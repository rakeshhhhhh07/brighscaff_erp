"""Customer statements with auditable rental timelines and explicit charge maths.

Date convention: the delivery day itself is NOT charged. Day 1 of the rental is the day
after delivery, and the return / as-of date is counted (delivery 01-10, return 06-10 = 5 days).
There is a single daily rate per item. Normal lines have a 30-day minimum (days 1-30), then
the same daily rate for every further day. Lines flagged "daily rental" have no minimum:
days elapsed x daily rate. This is displayed in exports so the customer can audit it.

Module layout
-------------
1. Shared helpers          - SQL access, money/date coercion, GST maths.
2. Charge computation      - return grouping and 30-day period splitting.
3. Timeline events         - one builder per event type on the statement.
4. Statement assembly      - ``build_ledger`` orchestrates the above.
5. Excel export            - one builder per worksheet.
6. PDF export              - one builder per table.
7. Blueprint views         - thin HTTP layer.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from html import escape
import re

from flask import request, make_response
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text
from .. import db
from ..security import login_required

blp = Blueprint(
    "ledgers",
    "ledgers",
    url_prefix="/api/ledgers",
    description="Rental charges, customer statements and exports",
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
DEFAULT_GST_RATE = 18
MINIMUM_RENTAL_DAYS = 30

STATEMENT_NOTE = (
    "Rental days are counted from the day after delivery up to and including the return/as-of "
    "date; the delivery day itself is not charged. "
    "Normal items are charged a 30-day minimum per unit at the daily rate, and every day after "
    "day 30 at the same daily rate. Items marked as daily rental are charged only for the days "
    "used, with no 30-day minimum. "
    "A discount (percentage or fixed) reduces the rental charges before GST and appears as a "
    "credit line; vehicle rent added at return is charged on the return date. "
    "Confirm this convention and any special commercial exceptions before treating the "
    "statement as a tax invoice."
)

STATEMENT_HEADERS = ["DATE", "BILL NO", "PARTICULARS", "RENT", "RECEIPT", "BALANCE"]

# Events sharing a date are ordered by this rank so a bill reads delivery -> return -> charge.
SORT_DELIVERY = 0
SORT_RETURN = 1
SORT_CHARGE = 2
SORT_DISCOUNT = 2.5  # a discount reads straight after the rental charges it reduces
SORT_RECEIPT = 3


# ---------------------------------------------------------------------------
# 1. Shared helpers
# ---------------------------------------------------------------------------


def rows(sql, p=None):
    return [dict(r._mapping) for r in db.session.execute(text(sql), p or {}).fetchall()]


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def date_text(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def as_date(value):
    """Coerce a DB value to ``date``.

    MySQL hands back ``date`` objects, but other drivers (and some column types)
    return ISO strings. Date arithmetic downstream assumes real ``date`` objects.
    """
    if value is None or isinstance(value, date):
        return value
    if hasattr(value, "date"):  # datetime
        return value.date()
    return date.fromisoformat(str(value)[:10])


def day_offset(anchor, days):
    """Return ``anchor`` shifted by ``days``, keeping the inclusive date convention explicit."""
    return anchor.fromordinal(anchor.toordinal() + days)


def gst_rate_of(line):
    """GST percentage applied to a delivery bill, or zero when GST is not opted in."""
    if not line.get("apply_gst"):
        return ZERO
    return Decimal(str(line.get("gst_rate") or DEFAULT_GST_RATE))


def gst_amount_of(line, base):
    """GST payable on ``base`` for a delivery bill."""
    rate = gst_rate_of(line)
    if not rate:
        return ZERO
    return money(base * rate / Decimal(100))


@dataclass(frozen=True)
class LineContext:
    """Per delivery-line facts reused by every charge and event builder."""

    line: dict
    issue: date
    issued: int
    initial_rate: Decimal
    extra_rate: Decimal
    is_daily: bool = False
    show_site: bool = False


@dataclass(frozen=True)
class ChargeWindow:
    """Totals describing one return group, shared across its 30-day period slices."""

    days: int
    first_days_actual: int
    minimum_per_unit: Decimal


# ---------------------------------------------------------------------------
# 2. Charge computation
# ---------------------------------------------------------------------------


def split_return_groups(ctx, returns, end_date):
    """Split an issued quantity into billable groups, one per return plus any outstanding.

    Returns ``(groups, return_events)``; each group carries the quantity and the date its
    rental period stops accruing.
    """
    outstanding = ctx.issued
    groups = []
    events = []
    for ret in returns:
        qty = int(ret["quantity_returned"])
        # Database records are validated at entry time; clamp defensively for old/inconsistent records.
        qty = min(qty, outstanding)
        if qty <= 0:
            continue
        outstanding -= qty
        groups.append(
            {
                "quantity": qty,
                "end_date": as_date(ret["return_date"]),
                "end_reason": "RETURN",
                "return_number": ret["return_number"],
                "condition": ret["item_condition"],
            }
        )
        events.append(build_return_event(ctx, ret, qty))
    # Anything not yet returned is charged through the statement end date.
    if outstanding > 0:
        groups.append(
            {
                "quantity": outstanding,
                "end_date": end_date,
                "end_reason": "AS_OF_DATE",
                "return_number": None,
                "condition": "OUTSTANDING",
            }
        )
    return groups, events


def rental_start(ctx):
    """First chargeable day: the day AFTER delivery."""
    return day_offset(ctx.issue, 1)


def build_first_period_spec(ctx, last, qty, window):
    """The opening rental month (days 1-30), where the 30-day minimum applies even on early return."""
    start = rental_start(ctx)
    first_end = min(last, day_offset(ctx.issue, MINIMUM_RENTAL_DAYS))
    per_unit = max(
        money(ctx.initial_rate * Decimal(window.first_days_actual)), window.minimum_per_unit
    )
    amount = money(per_unit * Decimal(qty))
    return {
        "period_start": min(start, first_end),
        "period_end": first_end,
        "label": "Initial 30-day minimum",
        "days": window.first_days_actual,
        "rate": ctx.initial_rate,
        "per_unit": per_unit,
        "amount": amount,
        "extra_days": 0,
        "formula": (
            f"{qty} × max(Rs. {ctx.initial_rate:,.2f} × {window.first_days_actual} day(s), "
            f"Rs. {ctx.initial_rate:,.2f} × 30-day minimum) = Rs. {amount:,.2f}"
        ),
    }


def build_daily_rental_spec(ctx, last, qty, window):
    """Daily rental: days used x daily rate. No 30-day minimum."""
    per_unit = money(ctx.initial_rate * Decimal(window.days))
    amount = money(per_unit * Decimal(qty))
    return {
        "period_start": min(rental_start(ctx), last),
        "period_end": last,
        "label": "Daily rental",
        "days": window.days,
        "rate": ctx.initial_rate,
        "per_unit": per_unit,
        "amount": amount,
        "extra_days": 0,
        "formula": (
            f"{qty} × Rs. {ctx.initial_rate:,.2f} × {window.days} day(s) = Rs. {amount:,.2f}"
        ),
    }


def build_extra_period_specs(ctx, qty, window):
    """Every further 30-day block after day 30, plus the final partial block, shown separately."""
    specs = []
    remaining = max(window.days - MINIMUM_RENTAL_DAYS, 0)
    cursor = day_offset(ctx.issue, MINIMUM_RENTAL_DAYS + 1)
    period_number = 1
    while remaining > 0:
        chunk_days = min(MINIMUM_RENTAL_DAYS, remaining)
        chunk_end = day_offset(cursor, chunk_days - 1)
        per_unit = money(ctx.extra_rate * Decimal(chunk_days))
        amount = money(per_unit * Decimal(qty))
        specs.append(
            {
                "period_start": cursor,
                "period_end": chunk_end,
                "label": f"Extra rental period {period_number} ({chunk_days} day(s))",
                "days": chunk_days,
                "rate": ctx.extra_rate,
                "per_unit": per_unit,
                "amount": amount,
                "extra_days": chunk_days,
                "formula": (
                    f"{qty} × Rs. {ctx.extra_rate:,.2f} × {chunk_days} extra day(s) "
                    f"= Rs. {amount:,.2f}"
                ),
            }
        )
        cursor = day_offset(cursor, chunk_days)
        remaining -= chunk_days
        period_number += 1
    return specs


def build_period_specs(ctx, last, qty):
    """Break one return group into its billable periods."""
    days = (last - ctx.issue).days  # delivery day not counted; return / as-of day counted
    if ctx.is_daily:
        window = ChargeWindow(days=days, first_days_actual=days, minimum_per_unit=ZERO)
        return [build_daily_rental_spec(ctx, last, qty, window)], window
    window = ChargeWindow(
        days=days,
        first_days_actual=min(days, MINIMUM_RENTAL_DAYS),
        minimum_per_unit=money(ctx.initial_rate * Decimal(MINIMUM_RENTAL_DAYS)),
    )
    specs = [build_first_period_spec(ctx, last, qty, window)]
    specs.extend(build_extra_period_specs(ctx, qty, window))
    return specs, window


def minimum_adjustment_per_unit(ctx, window):
    """How much of the opening charge is the 30-day minimum rather than elapsed days."""
    actual = money(ctx.initial_rate * Decimal(window.first_days_actual))
    return max(ZERO, window.minimum_per_unit - actual)


def monthly_rate_of(ctx):
    """Per-unit charge for one full 30-day rental month (the figure quoted on delivery)."""
    return money(ctx.initial_rate * Decimal(MINIMUM_RENTAL_DAYS))


# ---------------------------------------------------------------------------
# 3. Timeline events
# ---------------------------------------------------------------------------


def build_return_event(ctx, ret, qty):
    line = ctx.line
    return {
        "event_date": date_text(ret["return_date"]),
        "sort_order": SORT_RETURN,
        "reference_number": ret["return_number"],
        "transaction_type": "RETURN",
        "particulars": (
            f"{line['item_name']} — {qty} {line['unit']} returned from "
            f"{line['rental_number']} ({ret['item_condition']})"
        ),
        "debit": 0.0,
        "credit": 0.0,
        "source_order_id": int(line["rental_order_id"]),
        "rental_order_item_id": int(line["rental_order_item_id"]),
        "quantity": qty,
        "event_detail": (
            f"Return condition: {ret['item_condition']}; delivery {line['rental_number']} "
            f"issued {date_text(ctx.issue)}"
        ),
    }


def build_delivery_event(ctx):
    """Delivery is always represented, even when the amount is charged at return / statement date."""
    line = ctx.line
    monthly = monthly_rate_of(ctx)
    line_total = money(monthly * Decimal(ctx.issued))
    return {
        "event_date": date_text(ctx.issue),
        "sort_order": SORT_DELIVERY,
        "reference_number": line["rental_number"],
        "transaction_type": "DELIVERY",
        "particulars": (
            f"{line['item_name']} — {ctx.issued} {line['unit']} issued; "
            + (
                f"daily rental Rs. {ctx.initial_rate:,.2f}/day"
                if ctx.is_daily
                else f"Rs. {ctx.initial_rate:,.2f}/day (30-day minimum)"
            )
            # The site is stated once per delivery bill, on its first item line.
            + (f"; Site: {line['site_name']}" if ctx.show_site and line.get("site_name") else "")
        ),
        "site_name": line.get("site_name") or "",
        "debit": 0.0,
        "credit": 0.0,
        "source_order_id": int(line["rental_order_id"]),
        "rental_order_item_id": int(line["rental_order_item_id"]),
        "quantity": ctx.issued,
        # Structured fields consumed by the statement template exports.
        "item_name": line["item_name"],
        "unit": line["unit"],
        "daily_rate": float(ctx.initial_rate),
        "monthly_rate": float(monthly),
        "line_amount": float(line_total),
        "is_daily_rental": bool(ctx.is_daily),
        "event_detail": (
            f"Delivery batch {line['rental_number']}; delivered {date_text(ctx.issue)}, "
            f"rental days count from {date_text(rental_start(ctx))}"
        ),
    }


def build_charge_detail(ctx, group, spec, period_no, qty, window):
    """Full audit record for one charged period: inputs, rates, formula and totals."""
    line = ctx.line
    is_first = period_no == 1
    base = spec["amount"]
    gst = gst_amount_of(line, base)
    return {
        "rental_order_id": int(line["rental_order_id"]),
        "rental_order_item_id": int(line["rental_order_item_id"]),
        "rental_number": line["rental_number"],
        "item_code": line["item_code"],
        "item_name": line["item_name"],
        "unit": line["unit"],
        "issue_date": date_text(ctx.issue),
        "period_start": date_text(spec["period_start"]),
        "period_end": date_text(spec["period_end"]),
        "end_reason": group["end_reason"],
        "return_number": group["return_number"],
        "return_condition": group["condition"],
        "quantity": qty,
        "days_charged": window.days,
        "first_30_days_charged": window.first_days_actual,
        "extra_days": spec["extra_days"],
        "initial_daily_rate": float(ctx.initial_rate),
        "post_30_day_daily_rate": float(ctx.extra_rate),
        "first_period_per_unit": float(spec["per_unit"] if is_first else ZERO),
        "extra_days_per_unit": float(ZERO if is_first else spec["per_unit"]),
        "minimum_per_unit": float(window.minimum_per_unit),
        "minimum_adjustment_per_unit": float(
            minimum_adjustment_per_unit(ctx, window) if is_first else ZERO
        ),
        "amount_per_unit": float(spec["per_unit"]),
        "is_daily_rental": bool(ctx.is_daily),
        "period_days": spec["days"],
        "period_rate": float(spec["rate"]),
        "base_amount": float(base),
        "gst_rate": float(gst_rate_of(line)),
        "gst_amount": float(gst),
        "amount": float(money(base + gst)),
        "period_label": spec["label"],
        "formula": spec["formula"],
        "explanation": (
            f"{qty} {line['unit']} × {spec['days']} day(s), "
            f"{date_text(spec['period_start'])} to {date_text(spec['period_end'])}; "
            f"{spec['label']}; rate Rs. {spec['rate']:,.2f}/day; "
            f"end: {group['end_reason'].replace('_',' ').lower()}"
        ),
    }


def build_charge_event(ctx, spec, qty, detail, charge_date):
    line = ctx.line
    gst_suffix = ""
    if line.get("apply_gst"):
        gst_suffix = f"; GST {line.get('gst_rate') or DEFAULT_GST_RATE}% included"
    monthly = monthly_rate_of(ctx)
    return {
        "event_date": date_text(charge_date),
        "sort_order": SORT_CHARGE,
        "reference_number": line["rental_number"],
        "transaction_type": "RENTAL_CHARGE",
        "particulars": (
            f"{line['item_name']} — {qty} {line['unit']}; "
            f"{date_text(spec['period_start'])} to {date_text(spec['period_end'])}; "
            f"{spec['label']}" + gst_suffix
        ),
        "debit": detail["amount"],
        "credit": 0.0,
        "source_order_id": int(line["rental_order_id"]),
        "rental_order_item_id": int(line["rental_order_item_id"]),
        "quantity": qty,
        # Structured fields consumed by the statement template exports.
        "item_name": line["item_name"],
        "unit": line["unit"],
        "period_start": date_text(spec["period_start"]),
        "period_end": date_text(spec["period_end"]),
        "period_days": spec["days"],
        "full_month_amount": float(money(monthly * Decimal(qty))),
        "monthly_rate": float(monthly),
        "is_daily_rental": bool(ctx.is_daily),
        "event_detail": spec["formula"],
        "calculation": detail,
    }


def build_group_charges(ctx, group, end_date):
    """Charge events and audit details for one return group."""
    last = min(group["end_date"], end_date)
    if last < ctx.issue:
        return [], []
    qty = int(group["quantity"])
    specs, window = build_period_specs(ctx, last, qty)

    events = []
    details = []
    for period_no, spec in enumerate(specs, 1):
        # When returned before day 30, the minimum charge is posted on the return date.
        # When still out, the initial-period charge posts on day 30 (or the report as-of date).
        charge_date = spec["period_end"]
        if not spec["amount"]:
            continue
        detail = build_charge_detail(ctx, group, spec, period_no, qty, window)
        details.append(detail)
        events.append(build_charge_event(ctx, spec, qty, detail, charge_date))
    return events, details


def build_line_context(line, show_site=False):
    return LineContext(
        line=line,
        issue=as_date(line["line_issue_date"]),
        issued=int(line["quantity_issued"]),
        initial_rate=money(line["initial_daily_rate"]),
        # Single daily rate: there is no separate after-30-day rate any more.
        extra_rate=money(line["initial_daily_rate"]),
        is_daily=bool(line.get("is_daily_rental")),
        show_site=show_site,
    )


def collect_rental_events(rental_lines, end_date, returns_by_line=None):
    """Walk every delivery line and produce its return, charge and delivery events.

    ``returns_by_line`` lets a caller pre-load every return in one query, keyed by
    ``rental_order_item_id``. Without it each line is fetched individually, which is
    fine for a single statement but an N+1 when summarising every customer.
    """
    timeline = []
    calculations = []
    sites_shown = set()
    for line in rental_lines:
        first_line_of_bill = line["rental_order_id"] not in sites_shown
        sites_shown.add(line["rental_order_id"])
        ctx = build_line_context(line, show_site=first_line_of_bill)
        if ctx.issue > end_date:
            continue
        returns = (
            returns_by_line.get(int(line["rental_order_item_id"]), [])
            if returns_by_line is not None
            else fetch_line_returns(line["rental_order_item_id"], end_date)
        )
        groups, return_events = split_return_groups(ctx, returns, end_date)
        timeline.extend(return_events)
        for group_index, group in enumerate(groups, 1):
            charge_events, details = build_group_charges(ctx, group, end_date)
            calculations.extend(details)
            timeline.extend(charge_events)
        timeline.append(build_delivery_event(ctx))
    return timeline, calculations


def build_vehicle_rent_events(rental_lines, end_date):
    """Optional vehicle rent is charged once at the selected delivery/return stage."""
    events = []
    seen = set()
    for line in rental_lines:
        amount = money(line.get("vehicle_rent_amount") or 0)
        stage = line.get("vehicle_rent_stage")
        if amount <= 0 or not stage or (line["rental_order_id"], stage) in seen:
            continue
        seen.add((line["rental_order_id"], stage))
        event_dt = as_date(line["line_issue_date"])
        if stage == "RETURN":
            latest = fetch_latest_return_date(line["rental_order_id"], end_date)
            if latest:
                event_dt = as_date(latest)
        vehicle = f"{line.get('vehicle_type') or ''} {line.get('vehicle_number') or ''}".strip()
        events.append(
            {
                "event_date": date_text(event_dt),
                "sort_order": SORT_CHARGE,
                "reference_number": line["rental_number"],
                "transaction_type": "VEHICLE_RENT",
                "particulars": f"Vehicle rent — {vehicle}",
                "debit": float(amount),
                "credit": 0.0,
                "source_order_id": int(line["rental_order_id"]),
                "event_detail": "Vehicle rent",
            }
        )
    return events


def vehicle_label(vehicle_type, vehicle_number):
    return f"{vehicle_type or ''} {vehicle_number or ''}".strip()


def build_return_vehicle_events(adjustments):
    """Vehicle rent added from Return history is charged on that return's date."""
    events = []
    for adj in adjustments:
        amount = money(adj.get("vehicle_rent_amount"))
        if amount <= 0:
            continue
        vehicle = vehicle_label(adj.get("vehicle_type"), adj.get("vehicle_number"))
        events.append(
            {
                "event_date": date_text(adj["return_date"]),
                "sort_order": SORT_CHARGE,
                "reference_number": adj["rental_number"],
                "transaction_type": "VEHICLE_RENT",
                "particulars": (
                    f"Vehicle rent at return {adj['return_number']}"
                    + (f" — {vehicle}" if vehicle else "")
                ),
                "debit": float(amount),
                "credit": 0.0,
                "source_order_id": int(adj["rental_order_id"]),
                "event_detail": "Vehicle rent added from return history",
            }
        )
    return events


def discount_text(kind, value):
    if kind == "PERCENT":
        return f"{Decimal(str(value)):f}".rstrip("0").rstrip(".") + "%"
    return f"Rs. {money(value):,.2f} fixed"


def discount_net_amount(kind, value, base, remaining):
    """Discount on ``base``, never more than what is still undiscounted on the bill."""
    if kind == "PERCENT":
        amount = money(base * Decimal(str(value)) / Decimal(100))
    else:
        amount = money(value)
    return max(ZERO, min(amount, base, remaining))


def discount_sources(bill, bill_calcs, adjustments):
    """Every discount on one bill, as ``(date, type, value, base, label)``.

    A bill-level discount applies to all rental charges and posts on the last charge date.
    A return-level discount applies only to that return's charges and posts on the return date.
    """
    sources = []
    bill_base = sum((money(x["base_amount"]) for x in bill_calcs), ZERO)
    if (
        bill.get("discount_allowed")
        and bill.get("discount_type") in ("PERCENT", "FIXED")
        and money(bill.get("discount_value")) > 0
    ):
        sources.append(
            (
                max(x["period_end"] for x in bill_calcs),
                bill["discount_type"],
                bill["discount_value"],
                bill_base,
                "on rental charges",
            )
        )
    for adj in sorted(adjustments, key=lambda a: (date_text(a["return_date"]), a["return_number"])):
        if adj.get("discount_type") not in ("PERCENT", "FIXED") or money(adj["discount_value"]) <= 0:
            continue
        ret_base = sum(
            (money(x["base_amount"]) for x in bill_calcs if x.get("return_number") == adj["return_number"]),
            ZERO,
        )
        sources.append(
            (
                date_text(adj["return_date"]),
                adj["discount_type"],
                adj["discount_value"],
                ret_base,
                f"on rental charges of return {adj['return_number']}",
            )
        )
    return sources, bill_base


def compute_discounts(rental_lines, calculations, adjustments):
    """All discount credits for the statement, computed once and shared by events and summaries."""
    bills = {}
    for line in rental_lines:
        bills.setdefault(int(line["rental_order_id"]), line)
    discounts = []
    for order_id, bill in bills.items():
        bill_calcs = [x for x in calculations if x["rental_order_id"] == order_id]
        if not bill_calcs:
            continue
        order_adjustments = [a for a in adjustments if int(a["rental_order_id"]) == order_id]
        sources, bill_base = discount_sources(bill, bill_calcs, order_adjustments)
        remaining = bill_base
        for when, kind, value, base, label in sources:
            net = discount_net_amount(kind, value, base, remaining)
            if net <= 0:
                continue
            remaining -= net
            gst = gst_amount_of(bill, net)
            discounts.append(
                {
                    "rental_order_id": order_id,
                    "rental_number": bill["rental_number"],
                    "event_date": when,
                    "kind": kind,
                    "value": float(value),
                    "net": net,
                    "gst": gst,
                    "credit": money(net + gst),
                    "label": label,
                }
            )
    return discounts


def build_discount_events(discounts):
    events = []
    for d in discounts:
        gst_note = f"; incl. GST Rs. {d['gst']:,.2f}" if d["gst"] else ""
        events.append(
            {
                "event_date": d["event_date"],
                "sort_order": SORT_DISCOUNT,
                "reference_number": d["rental_number"],
                "transaction_type": "DISCOUNT",
                "particulars": (
                    f"Discount {discount_text(d['kind'], d['value'])} {d['label']} "
                    f"= Rs. {d['net']:,.2f}{gst_note}"
                ),
                "debit": 0.0,
                "credit": float(d["credit"]),
                "source_order_id": d["rental_order_id"],
                "event_detail": "Discount allowed on the delivery bill",
            }
        )
    return events


def build_payment_events(payment_rows):
    """Every recorded advance/return receipt is a credit against the same delivery bill."""
    return [
        {
            "event_date": date_text(p["payment_date"]),
            "sort_order": SORT_RECEIPT,
            "reference_number": p.get("reference_number") or p["rental_number"],
            "transaction_type": "RECEIPT",
            "particulars": (
                f"{p['payment_type']} payment — "
                f"{p.get('payment_method') or 'Method not specified'}"
            ),
            "debit": 0.0,
            "credit": float(money(p["amount"])),
            "source_order_id": int(p["rental_order_id"]),
            "payment_id": int(p["id"]),
            "event_detail": p.get("notes") or "",
        }
        for p in payment_rows
    ]


def build_manual_ledger_events(ledger):
    return [
        {
            "event_date": date_text(e["transaction_date"]),
            "sort_order": SORT_RECEIPT,
            "reference_number": e.get("reference_number") or "",
            "transaction_type": e.get("transaction_type") or "OTHER",
            "particulars": e.get("particulars") or "",
            "debit": float(money(e.get("debit"))),
            "credit": float(money(e.get("credit"))),
            "event_detail": "Manual ledger entry",
            "ledger_entry_id": int(e["id"]),
        }
        for e in ledger
    ]


# ---------------------------------------------------------------------------
# 4. Statement assembly
# ---------------------------------------------------------------------------


def resolve_period(start, end):
    try:
        start_date = date.fromisoformat(start) if start else date(1000, 1, 1)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError:
        abort(400, message="Dates must use YYYY-MM-DD format")
    if start_date > end_date:
        abort(400, message="From date cannot be after To date")
    return start_date, end_date


def fetch_customer(customer_id):
    row = db.session.execute(
        text("SELECT * FROM customers WHERE id=:id"), {"id": customer_id}
    ).fetchone()
    if not row:
        abort(404, message="Customer not found")
    return dict(row._mapping)


def fetch_manual_ledger_entries(customer_id, end_date):
    """Includes entries before the selected period so the opening balance is correct."""
    return rows(
        """SELECT id, transaction_date, reference_number, transaction_type, particulars,
               debit, credit
        FROM ledger_entries
        WHERE customer_id=:id AND transaction_date<=:end
        ORDER BY transaction_date, id""",
        {"id": customer_id, "end": end_date},
    )


def fetch_rental_lines(customer_id, end_date):
    return rows(
        """SELECT ro.id AS rental_order_id, ro.rental_number, ro.issue_date AS order_issue_date,
               ro.status AS order_status, ro.apply_gst, ro.gst_rate, ro.vehicle_rent_amount,
               ro.vehicle_rent_stage, ro.vehicle_type, ro.vehicle_number,
               roi.id AS rental_order_item_id, roi.quantity_issued, roi.initial_daily_rate,
               roi.post_30_day_daily_rate, roi.issue_date AS line_issue_date,
               COALESCE(roi.is_daily_rental,0) AS is_daily_rental,
               ro.site_name, COALESCE(ro.discount_allowed,0) AS discount_allowed,
               ro.discount_type, COALESCE(ro.discount_value,0) AS discount_value,
               i.item_code, i.item_name, i.unit
        FROM rental_orders ro
        JOIN rental_order_items roi ON roi.rental_order_id=ro.id
        JOIN items i ON i.id=roi.item_id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND roi.issue_date<=:end
        ORDER BY roi.issue_date, ro.id, roi.id""",
        {"id": customer_id, "end": end_date},
    )


def fetch_line_returns(rental_order_item_id, end_date):
    return rows(
        """SELECT rr.id AS return_id, rr.return_number, rr.return_date,
               rri.id AS return_line_id, rri.quantity_returned, rri.item_condition, rri.notes
        FROM rental_return_items rri
        JOIN rental_returns rr ON rr.id=rri.rental_return_id
        WHERE rri.rental_order_item_id=:id AND rr.return_date<=:end
        ORDER BY rr.return_date, rr.id, rri.id""",
        {"id": rental_order_item_id, "end": end_date},
    )


def fetch_latest_return_date(rental_order_id, end_date):
    return db.session.execute(
        text("""SELECT MAX(return_date) FROM rental_returns
            WHERE rental_order_id=:id AND return_date<=:end"""),
        {"id": rental_order_id, "end": end_date},
    ).scalar()


def fetch_payments(customer_id, end_date):
    return rows(
        """SELECT rp.*, ro.customer_id, ro.rental_number
        FROM rental_payments rp
        JOIN rental_orders ro ON ro.id=rp.rental_order_id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND rp.payment_date<=:end
        ORDER BY rp.payment_date, rp.id""",
        {"id": customer_id, "end": end_date},
    )


def fetch_return_adjustments(customer_id, end_date):
    """Vehicle rent / discount saved against return bills (voided returns are ignored)."""
    return rows(
        """SELECT rra.rental_return_id, rra.rental_order_id, rra.vehicle_rent_amount,
               rra.vehicle_type, rra.vehicle_number, rra.discount_type, rra.discount_value,
               rr.return_number, rr.return_date, ro.rental_number
        FROM rental_return_adjustments rra
        JOIN rental_returns rr ON rr.id=rra.rental_return_id
        JOIN rental_orders ro ON ro.id=rra.rental_order_id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND rr.return_date<=:end
              AND EXISTS (SELECT 1 FROM rental_return_items rri
                          WHERE rri.rental_return_id=rr.id)
        ORDER BY rr.return_date, rr.id""",
        {"id": customer_id, "end": end_date},
    )


def fetch_running_items(customer_id, end_date):
    """Items still with the customer at ``end_date``: issued quantity less everything returned.

    This drives the ``RUNNING ITEMS / NOS`` block at the foot of the statement.
    """
    running = rows(
        """SELECT i.item_code, i.item_name, i.unit,
               SUM(roi.quantity_issued) - COALESCE(SUM(ret.returned),0) AS outstanding
        FROM rental_orders ro
        JOIN rental_order_items roi ON roi.rental_order_id=ro.id
        JOIN items i ON i.id=roi.item_id
        LEFT JOIN (
            SELECT rri.rental_order_item_id, SUM(rri.quantity_returned) AS returned
            FROM rental_return_items rri
            JOIN rental_returns rr ON rr.id=rri.rental_return_id
            WHERE rr.return_date<=:end
            GROUP BY rri.rental_order_item_id
        ) ret ON ret.rental_order_item_id=roi.id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND roi.issue_date<=:end
        GROUP BY i.id, i.item_code, i.item_name, i.unit
        HAVING outstanding > 0
        ORDER BY i.item_name""",
        {"id": customer_id, "end": end_date},
    )
    for r in running:
        r["outstanding"] = int(r["outstanding"] or 0)
    return running


def fetch_return_history(customer_id, start_date, end_date):
    """A separate, fully auditable return history covering the selected period."""
    history = rows(
        """SELECT rr.return_date, DATE(rr.created_at) AS submitted_at, rr.return_number,
               ro.rental_number, roi.id AS rental_order_item_id,
               i.item_code, i.item_name, i.unit,
               rri.quantity_returned, rri.item_condition, rri.notes
        FROM rental_returns rr
        JOIN rental_orders ro ON ro.id=rr.rental_order_id
        JOIN rental_order_items roi ON roi.rental_order_id=ro.id
        JOIN rental_return_items rri
             ON rri.rental_order_item_id=roi.id AND rri.rental_return_id=rr.id
        JOIN items i ON i.id=roi.item_id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED'
              AND rr.return_date BETWEEN :start AND :end
        ORDER BY rr.return_date, rr.id, rri.id""",
        {"id": customer_id, "start": start_date, "end": end_date},
    )
    for r in history:
        r["return_date"] = date_text(r["return_date"])
        r["submitted_at"] = (
            r["submitted_at"].isoformat()
            if hasattr(r.get("submitted_at"), "isoformat")
            else str(r.get("submitted_at") or "")[:10]
        )
        r["quantity_returned"] = int(r["quantity_returned"])
    return history


def fetch_bill_summaries(customer_id, end_date, calculations, discounts=(), adjustments=()):
    """Bill-wise rental, discount, GST, vehicle rent, receipts and balance."""
    summaries = rows(
        """SELECT ro.id AS rental_order_id, ro.rental_number, ro.issue_date,
               COALESCE(ro.site_name,'') AS site_name,
               COALESCE(ro.vehicle_rent_amount,0) AS vehicle_rent_amount,
               COALESCE(ro.apply_gst,0) AS apply_gst,
               COALESCE(ro.gst_rate,18) AS gst_rate,
               COALESCE((SELECT SUM(rp.amount) FROM rental_payments rp
                         WHERE rp.rental_order_id=ro.id AND rp.payment_date<=:end),0) AS amount_paid
        FROM rental_orders ro
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND ro.issue_date<=:end
        ORDER BY ro.issue_date, ro.id""",
        {"id": customer_id, "end": end_date},
    )
    for bill in summaries:
        base = ZERO
        for x in calculations:
            if x["rental_order_id"] == int(bill["rental_order_id"]):
                base += money(x.get("base_amount", x["amount"]))
        order_id = int(bill["rental_order_id"])
        discount_net = sum((d["net"] for d in discounts if d["rental_order_id"] == order_id), ZERO)
        discount_gst = sum((d["gst"] for d in discounts if d["rental_order_id"] == order_id), ZERO)
        gst_total = money(gst_amount_of(bill, base) - discount_gst)
        vehicle_total = money(bill["vehicle_rent_amount"]) + sum(
            (money(a["vehicle_rent_amount"]) for a in adjustments if int(a["rental_order_id"]) == order_id),
            ZERO,
        )
        total_due = money(base - discount_net + gst_total + vehicle_total)
        paid = money(bill["amount_paid"])
        bill["rental_base"] = float(base)
        bill["discount_amount"] = float(discount_net)
        bill["vehicle_rent_amount"] = float(vehicle_total)
        bill["gst_amount"] = float(gst_total)
        bill["total_bill_amount"] = float(total_due)
        bill["amount_paid"] = float(paid)
        bill["balance_due"] = float(money(total_due - paid))
        bill["issue_date"] = date_text(bill["issue_date"])
    return summaries


def sort_timeline(timeline):
    timeline.sort(
        key=lambda e: (
            e["event_date"],
            e.get("sort_order", 9),
            str(e.get("reference_number") or ""),
            e.get("rental_order_item_id", 0),
        )
    )
    return timeline


def apply_running_balance(timeline, opening_balance, start_date, end_date):
    """Carry pre-period events into the opening balance, then run a balance over the period."""
    opening = money(opening_balance)
    for e in timeline:
        if e["event_date"] < start_date.isoformat():
            opening += money(e.get("debit")) - money(e.get("credit"))

    balance = opening
    entries = []
    for e in timeline:
        if not start_date.isoformat() <= e["event_date"] <= end_date.isoformat():
            continue
        balance += money(e.get("debit")) - money(e.get("credit"))
        entries.append(
            {
                **e,
                "transaction_date": e["event_date"],
                "running_balance": float(money(balance)),
                "debit": float(money(e.get("debit"))),
                "credit": float(money(e.get("credit"))),
            }
        )
    return opening, entries, balance


def period_totals(entries):
    """Debits raised and credits received inside the statement period."""
    charged = sum((money(e.get("debit")) for e in entries), ZERO)
    received = sum(
        (money(e.get("credit")) for e in entries if e.get("transaction_type") == "RECEIPT"), ZERO
    )
    return {"charged": float(charged), "received": float(received)}


def customer_contact_line(c):
    """``Sibi : 8075119101, Office : 0484 3527674`` — the numbers printed on the statement."""
    numbers = [c.get("main_mobile"), c.get("phone"), c.get("mobile_2"), c.get("mobile_3")]
    seen = []
    for n in numbers:
        n = str(n or "").strip()
        if n and n not in seen:
            seen.append(n)
    return ", ".join(seen)


def customer_summary(c):
    return {
        "id": int(c["id"]),
        "customer_code": c["customer_code"],
        "customer_name": c["customer_name"],
        "phone": c.get("phone"),
        "email": c.get("email"),
        "company": c.get("company"),
        "contact_line": customer_contact_line(c),
        "billing_address": c.get("billing_address"),
        "site_address": c.get("site_address"),
    }


def build_ledger(customer_id, start=None, end=None):
    """Assemble the full customer statement for the requested period."""
    c = fetch_customer(customer_id)
    start_date, end_date = resolve_period(start, end)

    ledger = fetch_manual_ledger_entries(customer_id, end_date)
    rental_lines = fetch_rental_lines(customer_id, end_date)

    timeline, calculations = collect_rental_events(rental_lines, end_date)
    adjustments = fetch_return_adjustments(customer_id, end_date)
    discounts = compute_discounts(rental_lines, calculations, adjustments)
    timeline.extend(build_vehicle_rent_events(rental_lines, end_date))
    timeline.extend(build_return_vehicle_events(adjustments))
    timeline.extend(build_discount_events(discounts))
    timeline.extend(build_payment_events(fetch_payments(customer_id, end_date)))
    timeline.extend(build_manual_ledger_events(ledger))
    sort_timeline(timeline)

    opening, entries, closing = apply_running_balance(
        timeline, c["opening_balance"], start_date, end_date
    )
    visible_calculations = [
        x for x in calculations if start_date.isoformat() <= x["period_end"] <= end_date.isoformat()
    ]
    totals = period_totals(entries)
    return {
        "bill_summaries": fetch_bill_summaries(
            customer_id, end_date, calculations, discounts, adjustments
        ),
        "customer": customer_summary(c),
        "period_start": None if start is None else start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "opening_balance": float(money(opening)),
        "entries": entries,
        "calculations": visible_calculations,
        "return_history": fetch_return_history(customer_id, start_date, end_date),
        "running_items": fetch_running_items(customer_id, end_date),
        "total_charged": totals["charged"],
        "total_received": totals["received"],
        "closing_balance": float(money(closing)),
        "note": STATEMENT_NOTE,
    }


# ---------------------------------------------------------------------------
# Shared export helpers
# ---------------------------------------------------------------------------


def entry_particulars(entry):
    """Statement text for an entry, expanded with the charge formula for rental charges."""
    particulars = entry.get("particulars", "")
    if entry.get("transaction_type") != "RENTAL_CHARGE":
        return particulars
    calc = entry.get("calculation") or {}
    if not calc:
        return particulars
    return (
        f"{calc.get('item_name','')} - {calc.get('quantity',0)} {calc.get('unit','')}; "
        f"{calc.get('period_start','')} TO {calc.get('period_end','')}; "
        f"{calc.get('period_label','')}; {calc.get('formula','')}"
    )


def display_date(value):
    """Statement date format, matching the reference workbooks: ``02.07.2026``."""
    return date.fromisoformat(value).strftime("%d.%m.%Y") if value else ""


def attachment_filename(data, customer_id, extension):
    code = re.sub(r"[^A-Za-z0-9_-]+", "-", data["customer"]["customer_code"]).strip("-")
    return f"bright-scaff-statement-{code or customer_id}.{extension}"


# ---------------------------------------------------------------------------
# Statement template model
#
# Both exports render the same list of rows, so the PDF and the workbook stay
# identical in structure. Each row is a dict:
#   kind     - row role, used only for styling (see STATEMENT ROW KINDS below)
#   date     - column A text
#   bill     - column B text
#   text     - column C text
#   rent     - column D number or None
#   receipt  - column E number or None
#   balance  - column F number or None
# ---------------------------------------------------------------------------

# Statement row kinds.
ROW_SITE = "SITE"  # "SITE: <name>" caption above a delivery
ROW_ITEM = "ITEM"  # one issued item: "SHUTTER 115   10 X 60 = 600"
ROW_ITEM_TOTAL = "ITEM_TOTAL"  # "TOTAL = 1650" under the issued items
ROW_CHARGE = "CHARGE"  # a rent period, carries RENT + BALANCE
ROW_RETURN = "RETURN"  # items returned; carries no money, only the return date
ROW_CREDIT = "CREDIT"  # receipt / discount, carries RECEIPT + BALANCE
ROW_OPENING = "OPENING"  # opening balance
ROW_SPACER = "SPACER"  # blank line between delivery bills and trailing sections
ROW_SECTION = "SECTION"  # bold caption such as "RUNNING ITEMS"
ROW_PLAIN = "PLAIN"  # free text inside a trailing section
ROW_TOTAL = "TOTAL"  # bold total inside a trailing section

# Colour scheme taken from Statement_template.docx. Each tone maps to
# (label colour for columns A-C, amount colour for columns D-F).
TONE_DEFAULT = "default"
TONE_RENT = "rent"
TONE_DISCOUNT = "discount"
TONE_RECEIPT = "receipt"
TONE_VEHICLE = "vehicle"
TONE_SECTION = "section"
TONE_RECEIVED = "received"
TONE_BALANCE = "balance"

BLACK = "000000"
RED = "FF0000"
PURPLE = "7030A0"
ORANGE = "BF4E14"
GREEN = "47D459"

TONE_COLORS = {
    TONE_DEFAULT: (BLACK, BLACK),
    TONE_RENT: (PURPLE, BLACK),  # rent periods read purple, the amount stays black
    TONE_DISCOUNT: (RED, BLACK),
    TONE_RECEIPT: (RED, ORANGE),  # red label, orange money
    TONE_VEHICLE: (GREEN, GREEN),
    TONE_SECTION: (PURPLE, PURPLE),
    TONE_RECEIVED: (ORANGE, ORANGE),
    TONE_BALANCE: (GREEN, GREEN),
}


def tone_colors(row):
    return TONE_COLORS.get(row.get("tone", TONE_DEFAULT), TONE_COLORS[TONE_DEFAULT])


def statement_row(
    kind, date_text_="", bill="", text="", rent=None, receipt=None, balance=None, tone=TONE_DEFAULT
):
    return {
        "kind": kind,
        "date": date_text_,
        "bill": bill,
        "text": text,
        "rent": rent,
        "receipt": receipt,
        "balance": balance,
        "tone": tone,
    }


ITEM_NAME_WIDTH = 28  # pads item names so the "QTY X RATE" columns line up


def item_line_text(entry):
    """``SHUTTER 115            10 X 60 = 600`` — the issued-item wording."""
    name = (entry.get("item_name") or "").upper()
    qty = int(entry.get("quantity") or 0)
    rate = entry.get("monthly_rate") or 0
    amount = entry.get("line_amount") or 0
    suffix = ""
    if entry.get("is_daily_rental"):
        rate = entry.get("daily_rate") or 0
        amount = rate * qty
        suffix = " /DAY"
    return f"{name:<{ITEM_NAME_WIDTH}} {qty} X {rate:.0f}{suffix} = {amount:.0f}"


def charge_line_text(entry):
    """``31.08.2026 TO 01.09.2026 [2 DAYS] [1650/30*2]`` — the rent period wording.

    A full 30-day block shows only the span. A part period also shows the pro-rata
    working so the customer can verify the figure by hand.
    """
    span = (
        f"{display_date(entry.get('period_start'))} TO {display_date(entry.get('period_end'))}"
    )
    days = int(entry.get("period_days") or 0)
    if entry.get("is_daily_rental"):
        return f"{span} [{days} DAYS]"
    if days >= MINIMUM_RENTAL_DAYS:
        return span
    full = entry.get("full_month_amount") or 0
    return f"{span} [{days} DAYS] [{full:.0f}/30*{days}]"


def delivery_block_rows(group):
    """Issued-item rows for one delivery bill, with its SITE caption and TOTAL line."""
    first = group[0]
    rows_out = []
    site = first.get("site_name")
    if site:
        rows_out.append(statement_row(ROW_SITE, text=f"SITE: {site.upper()}", tone=TONE_SECTION))

    total = sum(
        (e.get("daily_rate") or 0) * int(e.get("quantity") or 0)
        if e.get("is_daily_rental")
        else (e.get("line_amount") or 0)
        for e in group
    )
    for index, e in enumerate(group):
        rows_out.append(
            statement_row(
                ROW_ITEM,
                # Date and bill number are stated once, on the first item line.
                date_text_=display_date(first["transaction_date"]) if index == 0 else "",
                bill=(first.get("reference_number") or "") if index == 0 else "",
                text=item_line_text(e),
            )
        )
    # A single-item delivery needs no total; the item line already shows it.
    if len(group) > 1:
        rows_out.append(
            statement_row(ROW_ITEM_TOTAL, text=f"{'TOTAL':<{ITEM_NAME_WIDTH}} = {total:.0f}")
        )
    return rows_out


def credit_line_text(entry):
    """Wording for a receipt, discount or other credit row."""
    kind = entry.get("transaction_type")
    if kind == "DISCOUNT":
        return "DISCOUNT ALLOWED"
    if kind == "RECEIPT":
        label = "CASH RECEIVED"
        method = (entry.get("payment_method") or "").strip()
        if (entry.get("payment_type") or "").upper() == "ADVANCE":
            label = "CASH RECEIVED (ADVANCE)"
        return f"{label} [{method.upper()}]" if method else label
    return (entry.get("particulars") or "").upper()


def charge_row_text(entry):
    """Wording for a debit row: rent periods keep the reference format, others read plainly."""
    if entry.get("transaction_type") == "RENTAL_CHARGE":
        return charge_line_text(entry)
    if entry.get("transaction_type") == "VEHICLE_RENT":
        return "VEHICLE RENT ADDED"
    return (entry.get("particulars") or "").upper()


def money_tone(entry):
    """Template colour for a money row, keyed on what the event is."""
    kind = entry.get("transaction_type")
    if kind == "VEHICLE_RENT":
        return TONE_VEHICLE
    if kind == "DISCOUNT":
        return TONE_DISCOUNT
    if kind == "RECEIPT":
        return TONE_RECEIPT
    if kind == "RENTAL_CHARGE":
        return TONE_RENT
    return TONE_DEFAULT


# Events that print their own date and bill number in columns A and B.
# Rent periods do not: they belong to the delivery above them, and their dates
# are already stated inside the PARTICULARS text.
DATED_EVENT_TYPES = {"DELIVERY", "RETURN", "RECEIPT", "VEHICLE_RENT", "DISCOUNT"}


def money_row(entry):
    """One debit or credit row. The balance is filled in later, in display order."""
    debit = float(entry.get("debit") or 0)
    credit = float(entry.get("credit") or 0)
    dated = entry.get("transaction_type") in DATED_EVENT_TYPES
    return statement_row(
        ROW_CHARGE if debit else ROW_CREDIT,
        date_text_=display_date(entry.get("transaction_date")) if dated else "",
        bill=str(entry.get("reference_number") or "") if dated else "",
        text=charge_row_text(entry) if debit else credit_line_text(entry),
        rent=debit or None,
        receipt=credit or None,
        tone=money_tone(entry),
    )


def return_row(entry):
    """A return is shown for its date and bill number; it moves no money itself."""
    qty = int(entry.get("quantity") or 0)
    name = (entry.get("item_name") or "").upper()
    label = f"{name} RETURNED" if name else "RETURNED"
    return statement_row(
        ROW_RETURN,
        date_text_=display_date(entry.get("transaction_date")),
        bill=str(entry.get("reference_number") or ""),
        text=f"{label:<{ITEM_NAME_WIDTH}} {qty}" if name else label,
        tone=TONE_RENT,
    )


def blank_repeated_keys(rows_out):
    """Leave the date and bill cells blank when they repeat, as the reference does."""
    last_date = None
    last_bill = None
    for row in rows_out:
        if row["kind"] == ROW_SPACER:
            # A new block starts after a gap, so the next date always reprints.
            last_date = last_bill = None
            continue
        if row["date"]:
            if row["date"] == last_date:
                row["date"] = ""
            else:
                last_date = row["date"]
        if row["bill"]:
            if row["bill"] == last_bill:
                row["bill"] = ""
            else:
                last_bill = row["bill"]
    return rows_out


def statement_blocks(entries):
    """Group the timeline into dated blocks, in the layout the template specifies.

    A delivery block holds its issued items, their TOTAL, and the rent periods billed
    against that delivery, so a bill reads as one unit. Receipts, discounts and vehicle
    rent are standalone blocks. Blocks are then ordered by date.
    """
    deliveries = {}
    charges = {}
    returns = {}
    blocks = []
    for e in entries:
        kind = e.get("transaction_type")
        order_id = e.get("source_order_id")
        if kind == "DELIVERY":
            deliveries.setdefault(order_id, []).append(e)
        elif kind == "RENTAL_CHARGE":
            charges.setdefault(order_id, []).append(e)
        elif kind == "RETURN":
            returns.setdefault(order_id, []).append(e)
        elif float(e.get("debit") or 0) or float(e.get("credit") or 0):
            blocks.append((e["transaction_date"], 1, str(e.get("reference_number") or ""), [e]))

    for order_id, group in deliveries.items():
        bill_rows = delivery_block_rows(group)
        # Rent periods and returns belong to the bill they were raised against, so
        # they print inside its block in date order.
        followups = charges.pop(order_id, []) + returns.pop(order_id, [])
        for event in sorted(followups, key=lambda c: (c["transaction_date"], c.get("sort_order", 9))):
            bill_rows.append(
                return_row(event)
                if event.get("transaction_type") == "RETURN"
                else money_row(event)
            )
        blocks.append(
            (group[0]["transaction_date"], 0, str(group[0].get("reference_number") or ""), bill_rows)
        )

    # Charges and returns whose delivery falls outside the period still have to be shown.
    for group in charges.values():
        for charge in group:
            blocks.append(
                (charge["transaction_date"], 1, str(charge.get("reference_number") or ""), [charge])
            )
    for group in returns.values():
        for ret in group:
            blocks.append(
                (ret["transaction_date"], 1, str(ret.get("reference_number") or ""), [ret])
            )

    blocks.sort(key=lambda b: (b[0], b[1], b[2]))
    return blocks


def as_statement_row(item):
    """Delivery blocks are already template rows; standalone events are raw entries."""
    if isinstance(item, dict) and "kind" in item:
        return item
    if item.get("transaction_type") == "RETURN":
        return return_row(item)
    return money_row(item)


DELIVERY_BLOCK_RANK = 0  # see statement_blocks(): rank 0 is a delivery bill


def transaction_rows(entries):
    """Statement body: each delivery bill starts on a new line after a blank row."""
    out = []
    for index, (_date, rank, _ref, payload) in enumerate(statement_blocks(entries)):
        # A delivery bill always opens a fresh block, so the previous one is closed
        # off with a blank line. Standalone events continue on the next line.
        if index and rank == DELIVERY_BLOCK_RANK:
            out.append(statement_row(ROW_SPACER))
        out.extend(as_statement_row(item) for item in payload)
    return blank_repeated_keys(out)


def apply_display_balance(rows_out, opening_balance):
    """Run the balance down the rows in the order they are printed."""
    balance = money(opening_balance)
    for row in rows_out:
        if row["kind"] not in (ROW_CHARGE, ROW_CREDIT):
            continue
        balance += money(row["rent"]) - money(row["receipt"])
        row["balance"] = float(balance)
    return float(balance)


def running_items_rows(data):
    """The ``RUNNING ITEMS / NOS`` block: stock still with the customer."""
    items = data.get("running_items") or []
    if not items:
        return []
    out = [
        statement_row(ROW_SPACER),
        statement_row(ROW_SECTION, text="RUNNING ITEMS", rent="NOS", tone=TONE_SECTION),
    ]
    for item in items:
        out.append(
            statement_row(ROW_PLAIN, text=(item["item_name"] or "").upper(), rent=item["outstanding"])
        )
    return out


def payments_rows(data, closing_balance):
    """The closing ``PAYMENTS`` block: what was received and what is still to collect."""
    out = [
        statement_row(ROW_SPACER),
        statement_row(ROW_SECTION, text="PAYMENTS", tone=TONE_SECTION),
    ]
    for entry in data["entries"]:
        if entry.get("transaction_type") != "RECEIPT":
            continue
        out.append(
            statement_row(
                ROW_PLAIN,
                date_text_=display_date(entry.get("transaction_date")),
                text=credit_line_text(entry),
                receipt=float(entry.get("credit") or 0),
                tone=TONE_RECEIPT,
            )
        )
    out.append(
        statement_row(
            ROW_TOTAL,
            text="TOTAL AMOUNT RECEIVED",
            receipt=data.get("total_received", 0),
            tone=TONE_RECEIVED,
        )
    )
    out.append(
        statement_row(
            ROW_TOTAL, text="BALANCE AMOUNT TO GET", balance=closing_balance, tone=TONE_BALANCE
        )
    )
    return out


def statement_rows(data):
    """The complete statement, shared by the Excel and PDF exports."""
    out = []
    if data.get("opening_balance"):
        out.append(
            statement_row(
                ROW_OPENING, text="OPENING BALANCE", balance=float(data["opening_balance"])
            )
        )
    body = transaction_rows(data["entries"])
    # Deliveries are printed with their own rent periods, so the balance is run down
    # the printed order rather than reusing the chronological running balance.
    closing = apply_display_balance(body, data.get("opening_balance") or 0)
    if not body:
        out.append(statement_row(ROW_PLAIN, text="No transactions in the selected period"))
        closing = float(data["closing_balance"])
    out.extend(body)
    out.append(
        statement_row(ROW_TOTAL, text="CLOSING BALANCE", balance=closing, tone=TONE_BALANCE)
    )
    out.extend(running_items_rows(data))
    out.extend(payments_rows(data, closing))
    return out


# ---------------------------------------------------------------------------
# 5. Excel export
# ---------------------------------------------------------------------------


def excel_borders():
    from openpyxl.styles import Side

    return Side(style="thin", color="000000"), Side(style="medium", color="000000")


def statement_title(data):
    """``SIBI ABRAHAM (02.07.2026 - 14.10.2026)`` — customer plus the period covered."""
    name = (data["customer"]["customer_name"] or "").upper()
    start = display_date(data.get("period_start")) if data.get("period_start") else ""
    end = display_date(data["period_end"])
    return f"{name} ({start} - {end})" if start else f"{name} (UP TO {end})"


def statement_contact(data):
    """``<numbers>, <company>`` — the contact strip under the customer name."""
    c = data["customer"]
    parts = [c.get("contact_line") or c.get("phone"), c.get("company")]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def write_statement_header(ws, data):
    """Title, contact strip and column headings, matching the reference workbook."""
    from openpyxl.styles import Font, Border, Alignment

    thin, _medium = excel_borders()
    box = Border(top=thin, bottom=thin, left=thin, right=thin)
    centre = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A1:E1")
    ws["A1"] = statement_title(data)
    # The template prints the customer line in red; everything else is black.
    ws["A1"].font = Font(name="Calibri", size=12, bold=True, color=RED)
    ws["A1"].alignment = centre
    ws["F1"] = data["customer"]["customer_code"]
    ws["F1"].font = Font(name="Calibri", size=11, bold=True, color=RED)
    ws["F1"].alignment = centre

    ws.merge_cells("A2:E2")
    ws["A2"] = statement_contact(data)
    ws["A2"].font = Font(name="Calibri", size=11, bold=True)
    ws["A2"].alignment = centre
    ws["F2"] = display_date(data["period_end"])
    ws["F2"].font = Font(name="Calibri", size=11, bold=True)
    ws["F2"].alignment = centre

    for col in range(1, 7):
        ws.cell(1, col).border = box
        ws.cell(2, col).border = box
        cell = ws.cell(3, col, STATEMENT_HEADERS[col - 1])
        cell.font = Font(name="Calibri", size=11, bold=True)
        cell.alignment = centre
        cell.border = box

    ws.row_dimensions[1].height = 16.5
    ws.row_dimensions[2].height = 15.75


def group_statement_entries(entries):
    """Group delivery item rows by delivery bill; every other event stays on its own row."""
    groups = {}
    for e in entries:
        if e.get("transaction_type") == "DELIVERY":
            key = ("DELIVERY", e["transaction_date"], e.get("reference_number") or "")
        else:
            key = ("SINGLE", id(e))
        groups.setdefault(key, []).append(e)
    return sorted(
        groups.values(),
        key=lambda g: (
            g[0]["transaction_date"],
            0 if g[0].get("transaction_type") == "DELIVERY" else 1,
            str(g[0].get("reference_number") or ""),
        ),
    )


# Kinds rendered in bold, like the handwritten totals in the reference workbook.
BOLD_ROW_KINDS = {ROW_ITEM_TOTAL, ROW_SECTION, ROW_TOTAL, ROW_OPENING, ROW_SITE}


def balance_formula(row_index, previous_balance_row, row):
    """Live Excel formula for the BALANCE cell, as the reference workbook uses.

    Rent adds (``=F7+D8``), a receipt subtracts (``=F37-E38``). The first balance on the
    sheet has nothing to carry forward, so it simply reads its own rent cell.
    """
    sign = "+" if row["rent"] is not None else "-"
    own = f"D{row_index}" if row["rent"] is not None else f"E{row_index}"
    if previous_balance_row is None:
        return f"={own}" if sign == "+" else f"=-{own}"
    return f"=F{previous_balance_row}{sign}{own}"


def write_statement_row(ws, row_index, row, previous_balance_row):
    """Write one template row across columns A-F and style it for its kind.

    Returns the row that later rows should carry their balance forward from.
    """
    from openpyxl.styles import Font, Border, Alignment

    thin, _medium = excel_borders()
    box = Border(top=thin, bottom=thin, left=thin, right=thin)
    kind = row["kind"]
    if kind == ROW_SPACER:
        return previous_balance_row

    balance = row["balance"]
    carries_balance = kind in (ROW_CHARGE, ROW_CREDIT)
    if carries_balance:
        # Keep the arithmetic auditable and editable inside Excel.
        balance = balance_formula(row_index, previous_balance_row, row)
    elif kind == ROW_TOTAL and balance is not None and previous_balance_row:
        # Closing balance / balance to collect simply restate the last running balance.
        balance = f"=F{previous_balance_row}"

    values = [row["date"], row["bill"], row["text"], row["rent"], row["receipt"], balance]
    bold = kind in BOLD_ROW_KINDS
    # Columns A-C carry the label colour, D-F the amount colour (see TONE_COLORS).
    label_color, amount_color = tone_colors(row)
    # Column C holds item lines and formulas, which are read left-aligned;
    # every other column is centred as in the reference workbook.
    text_left = kind in (ROW_ITEM, ROW_ITEM_TOTAL, ROW_SITE)
    for col, value in enumerate(values, 1):
        cell = ws.cell(row_index, col, value if value not in ("", None) else None)
        cell.font = Font(
            name="Calibri",
            size=11,
            bold=bold,
            color=label_color if col <= 3 else amount_color,
        )
        cell.border = box
        cell.alignment = Alignment(
            horizontal="left" if (col == 3 and text_left) else "center", vertical="center"
        )
        # Money gets two decimals; plain counts (running items) stay whole numbers.
        if col >= 4 and isinstance(value, float):
            cell.number_format = "#,##0.00"
        elif col >= 4 and isinstance(value, int) and not isinstance(value, bool):
            cell.number_format = "#,##0"
        if col == 6 and carries_balance:
            cell.number_format = "#,##0.00"

    if kind == ROW_OPENING or carries_balance:
        return row_index
    return previous_balance_row


def style_statement_sheet(ws, last_row):
    """Column widths, print setup and the frozen heading, as in the reference workbook."""
    from openpyxl.utils import get_column_letter

    for col, width in enumerate([12, 13, 58, 13, 13, 14], 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:3"
    ws.print_area = f"A1:F{last_row}"


def write_statement_sheet(ws, data):
    """Sheet 1: the chronological customer statement, in the agreed template layout."""
    ws.title = "Customer Statement"
    write_statement_header(ws, data)

    row_index = 4
    previous_balance_row = None
    for row in statement_rows(data):
        previous_balance_row = write_statement_row(ws, row_index, row, previous_balance_row)
        row_index += 1
    style_statement_sheet(ws, row_index - 1)


RENTAL_DETAIL_HEADERS = [
    "DELIVERY BILL",
    "ITEM",
    "QTY",
    "ISSUE DATE",
    "RETURN / AS-OF DATE",
    "RETURN BILL",
    "PERIOD",
    "DAYS",
    "RATE / DAY",
    "CALCULATION",
    "AMOUNT",
]


def rental_detail_row(x):
    return [
        x["rental_number"],
        x["item_name"],
        x["quantity"],
        x["issue_date"],
        x["period_end"],
        x.get("return_number") or "",
        x["period_label"],
        x["period_days"],
        x["period_rate"],
        x["formula"],
        x["amount"],
    ]


def return_event_row(x):
    return [
        x["rental_number"],
        x["item_name"],
        x["quantity_returned"],
        "",
        x["return_date"],
        x["return_number"],
        "RETURN EVENT",
        "",
        "",
        (
            f"Actual return: {x['return_date']}; bill submitted: {x.get('submitted_at','')}; "
            f"condition: {x['item_condition']}"
        ),
        0,
    ]


def write_rental_details_sheet(wb, data):
    """Sheet 2: a compact supporting sheet preserving full formula-level transparency."""
    from openpyxl.styles import Font, Border, Alignment
    from openpyxl.utils import get_column_letter

    thin, medium = excel_borders()
    calc = wb.create_sheet("Rental Details")
    calc.append(["RENTAL CALCULATION DETAILS"])
    calc.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(RENTAL_DETAIL_HEADERS))
    calc["A1"].font = Font(name="Arial", size=12, bold=True)

    calc.append(RENTAL_DETAIL_HEADERS)
    for c in calc[2]:
        c.font = Font(name="Arial", bold=True)
        c.border = Border(top=medium, bottom=medium)
        c.alignment = Alignment(wrap_text=True)

    for x in data["calculations"]:
        calc.append(rental_detail_row(x))
    for x in data["return_history"]:
        calc.append(return_event_row(x))

    for cells in calc.iter_rows():
        for cell in cells:
            cell.font = cell.font.copy(name="Arial", size=9)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row > 1:
                cell.border = Border(bottom=thin)
            if cell.column == 11 and cell.row > 2:
                cell.number_format = "#,##0.00"
    for col, width in enumerate([21, 25, 10, 15, 20, 22, 30, 10, 15, 75, 16], 1):
        calc.column_dimensions[get_column_letter(col)].width = width
    calc.freeze_panes = "A3"
    calc.auto_filter.ref = f"A2:K{max(2, calc.max_row)}"
    calc.sheet_view.showGridLines = False
    calc.page_setup.orientation = "landscape"
    calc.page_setup.fitToWidth = 1
    calc.page_setup.fitToHeight = 0
    calc.sheet_properties.pageSetUpPr.fitToPage = True


BILL_SUMMARY_HEADERS = [
    "BILL NO",
    "SITE",
    "DATE",
    "RENTAL",
    "DISCOUNT",
    "GST 18%",
    "VEHICLE RENT",
    "BILL TOTAL",
    "PAID",
    "BALANCE",
]


def write_bill_summary_sheet(wb, data):
    """Sheet 3: bill-wise totals, receipts and balances."""
    from openpyxl.styles import Font, Border, Alignment
    from openpyxl.utils import get_column_letter

    thin, medium = excel_borders()
    black = "000000"
    billws = wb.create_sheet("Bill Summary")
    billws.append(["BILL-WISE PAYMENT SUMMARY"])
    billws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
    billws["A1"].font = Font(name="Arial", size=12, bold=True, color=black)

    billws.append(BILL_SUMMARY_HEADERS)
    for cell in billws[2]:
        cell.font = Font(name="Arial", bold=True, color=black)
        cell.border = Border(top=medium, bottom=medium)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for bill in data.get("bill_summaries", []):
        billws.append(
            [
                bill["rental_number"],
                bill.get("site_name") or "",
                display_date(bill["issue_date"]),
                bill["rental_base"],
                bill.get("discount_amount", 0),
                bill["gst_amount"],
                bill["vehicle_rent_amount"],
                bill["total_bill_amount"],
                bill["amount_paid"],
                bill["balance_due"],
            ]
        )

    for cells in billws.iter_rows(min_row=3):
        for cell in cells:
            cell.font = Font(name="Arial", size=9, color=black)
            cell.alignment = Alignment(
                horizontal="left" if cell.column in (1, 2) else "center",
                vertical="center",
            )
            cell.border = Border(bottom=thin)
            if cell.column >= 4:
                cell.number_format = "#,##0.00"
    for col, width in enumerate([22, 24, 15, 16, 14, 14, 16, 16, 14, 16], 1):
        billws.column_dimensions[get_column_letter(col)].width = width
    billws.sheet_view.showGridLines = False
    billws.freeze_panes = "A3"


def build_statement_workbook(data):
    from openpyxl import Workbook

    wb = Workbook()
    write_statement_sheet(wb.active, data)
    write_rental_details_sheet(wb, data)
    write_bill_summary_sheet(wb, data)
    return wb


# ---------------------------------------------------------------------------
# 6. PDF export
# ---------------------------------------------------------------------------

PDF_SUMMARY_HEADERS = [
    "BILL NO",
    "SITE",
    "DATE",
    "RENTAL",
    "DISCOUNT",
    "GST",
    "VEHICLE",
    "TOTAL",
    "PAID",
    "BALANCE",
]


def safe(value):
    return escape(str(value if value is not None else ""))


def pdf_styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="StmtSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.black,
            spaceAfter=0,
        )
    )
    # Item lines and formulas are monospaced so the "QTY X RATE = AMOUNT" columns
    # line up exactly as they do in the reference workbook.
    styles.add(
        ParagraphStyle(
            name="StmtMono",
            parent=styles["StmtSmall"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="StmtMonoBold", parent=styles["StmtMono"], fontName="Courier-Bold"
        )
    )
    styles.add(
        ParagraphStyle(name="StmtBold", parent=styles["StmtSmall"], fontName="Helvetica-Bold")
    )
    return styles


def pdf_table_style(padding, amount_from_column):
    """Plain black-and-white rules. No colored fills, boxes or icons."""
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (amount_from_column, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), padding),
            ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ]
    )


def pdf_header_story(data, styles):
    """Title block mirroring rows 1-2 of the workbook."""
    from reportlab.platypus import Paragraph, Spacer

    contact = statement_contact(data)
    story = [Paragraph(f"<b>{safe(statement_title(data))}</b>", styles["Title"])]
    if contact:
        story.append(Paragraph(safe(contact), styles["StmtBold"]))
    story.append(
        Paragraph(f"Statement date: {safe(display_date(data['period_end']))}", styles["StmtSmall"])
    )
    story.append(Spacer(1, 8))
    return story


# Row kinds that print in bold in the PDF, matching the workbook.
PDF_BOLD_KINDS = {ROW_ITEM_TOTAL, ROW_SECTION, ROW_TOTAL, ROW_OPENING, ROW_SITE}
# Row kinds whose column C is monospaced so the figures align in a column.
PDF_MONO_KINDS = {ROW_ITEM, ROW_ITEM_TOTAL}


def pdf_amount(value):
    """Money prints with two decimals; plain counts (running items) print as integers."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def pdf_statement_row(row, styles):
    """Render one template row as a PDF table row, in the template's colours."""
    from reportlab.platypus import Paragraph

    kind = row["kind"]
    bold = kind in PDF_BOLD_KINDS
    if kind in PDF_MONO_KINDS:
        text_style = styles["StmtMonoBold"] if bold else styles["StmtMono"]
    else:
        text_style = styles["StmtBold"] if bold else styles["StmtSmall"]
    cell_style = styles["StmtBold"] if bold else styles["StmtSmall"]

    label_color, amount_color = tone_colors(row)
    # Paragraph collapses runs of spaces, so the padded item columns are kept with &nbsp;.
    text = safe(row["text"]).replace("  ", "&nbsp;&nbsp;")

    def tinted(markup, style, color):
        return Paragraph(f'<font color="#{color}">{markup}</font>', style)

    return [
        tinted(safe(row["date"]), cell_style, label_color),
        tinted(safe(row["bill"]), cell_style, label_color),
        tinted(text, text_style, label_color),
        tinted(pdf_amount(row["rent"]), cell_style, amount_color),
        tinted(pdf_amount(row["receipt"]), cell_style, amount_color),
        tinted(pdf_amount(row["balance"]), cell_style, amount_color),
    ]


def pdf_statement_table(data, styles):
    """The statement body, built from the same template rows as the workbook."""
    from reportlab.platypus import Paragraph, Table

    small = styles["StmtSmall"]
    table_data = [[Paragraph(f"<b>{h}</b>", small) for h in STATEMENT_HEADERS]]
    for row in statement_rows(data):
        if row["kind"] == ROW_SPACER:
            table_data.append([Paragraph("", small)] * 6)
            continue
        table_data.append(pdf_statement_row(row, styles))

    table = Table(table_data, colWidths=[66, 72, 396, 62, 62, 72], repeatRows=1, hAlign="LEFT")
    table.setStyle(pdf_table_style(padding=3, amount_from_column=3))
    return table


def pdf_bill_summary_story(data, styles):
    from reportlab.platypus import Paragraph, Spacer, Table

    small = styles["StmtSmall"]
    summary_rows = [[Paragraph(f"<b>{h}</b>", small) for h in PDF_SUMMARY_HEADERS]]
    for bill in data["bill_summaries"]:
        summary_rows.append(
            [
                Paragraph(safe(bill["rental_number"]), small),
                Paragraph(safe(bill.get("site_name") or ""), small),
                Paragraph(safe(display_date(bill["issue_date"])), small),
                Paragraph(f"{bill['rental_base']:,.2f}", small),
                Paragraph(f"{bill.get('discount_amount', 0):,.2f}", small),
                Paragraph(f"{bill['gst_amount']:,.2f}", small),
                Paragraph(f"{bill['vehicle_rent_amount']:,.2f}", small),
                Paragraph(f"{bill['total_bill_amount']:,.2f}", small),
                Paragraph(f"{bill['amount_paid']:,.2f}", small),
                Paragraph(f"{bill['balance_due']:,.2f}", small),
            ]
        )
    summary_table = Table(
        summary_rows,
        colWidths=[74, 84, 54, 58, 54, 48, 54, 58, 54, 58],
        repeatRows=1,
        hAlign="LEFT",
    )
    summary_table.setStyle(pdf_table_style(padding=3, amount_from_column=3))
    return [
        Spacer(1, 14),
        Paragraph("<b>BILL-WISE PAYMENT SUMMARY</b>", styles["Normal"]),
        Spacer(1, 5),
        summary_table,
    ]


def build_statement_pdf(data):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28
    )
    styles = pdf_styles()
    story = pdf_header_story(data, styles)
    # The statement table already closes with CLOSING BALANCE, RUNNING ITEMS and PAYMENTS.
    story.append(pdf_statement_table(data, styles))
    if data.get("bill_summaries"):
        story.extend(pdf_bill_summary_story(data, styles))
    story.extend([Spacer(1, 12), Paragraph(f"<i>{safe(data['note'])}</i>", styles["StmtSmall"])])
    doc.build(story)
    return buffer


# ---------------------------------------------------------------------------
# 7. Blueprint views
# ---------------------------------------------------------------------------


def ledger_from_request(customer_id):
    return build_ledger(customer_id, request.args.get("start"), request.args.get("end"))


def fetch_all_rental_lines(end_date):
    """Every customer's delivery lines in one query, grouped by customer id."""
    lines = rows(
        """SELECT ro.customer_id, ro.id AS rental_order_id, ro.rental_number,
               ro.issue_date AS order_issue_date, ro.status AS order_status,
               ro.apply_gst, ro.gst_rate, ro.vehicle_rent_amount, ro.vehicle_rent_stage,
               ro.vehicle_type, ro.vehicle_number,
               roi.id AS rental_order_item_id, roi.quantity_issued, roi.initial_daily_rate,
               roi.post_30_day_daily_rate, roi.issue_date AS line_issue_date,
               COALESCE(roi.is_daily_rental,0) AS is_daily_rental,
               ro.site_name, COALESCE(ro.discount_allowed,0) AS discount_allowed,
               ro.discount_type, COALESCE(ro.discount_value,0) AS discount_value,
               i.item_code, i.item_name, i.unit
        FROM rental_orders ro
        JOIN rental_order_items roi ON roi.rental_order_id=ro.id
        JOIN items i ON i.id=roi.item_id
        WHERE ro.status<>'CANCELLED' AND roi.issue_date<=:end
        ORDER BY roi.issue_date, ro.id, roi.id""",
        {"end": end_date},
    )
    by_customer = {}
    for line in lines:
        by_customer.setdefault(int(line["customer_id"]), []).append(line)
    return by_customer


def fetch_all_line_returns(end_date):
    """Every return in the period, grouped by ``rental_order_item_id``."""
    returns = rows(
        """SELECT rri.rental_order_item_id, rr.id AS return_id, rr.return_number,
               rr.return_date, rri.id AS return_line_id, rri.quantity_returned,
               rri.item_condition, rri.notes
        FROM rental_return_items rri
        JOIN rental_returns rr ON rr.id=rri.rental_return_id
        WHERE rr.return_date<=:end
        ORDER BY rr.return_date, rr.id, rri.id""",
        {"end": end_date},
    )
    by_line = {}
    for ret in returns:
        by_line.setdefault(int(ret["rental_order_item_id"]), []).append(ret)
    return by_line


def fetch_all_return_adjustments(end_date):
    """Return-level vehicle rent and discounts, grouped by customer id."""
    adjustments = rows(
        """SELECT ro.customer_id, rra.rental_return_id, rra.rental_order_id,
               rra.vehicle_rent_amount, rra.vehicle_type, rra.vehicle_number,
               rra.discount_type, rra.discount_value,
               rr.return_number, rr.return_date, ro.rental_number
        FROM rental_return_adjustments rra
        JOIN rental_returns rr ON rr.id=rra.rental_return_id
        JOIN rental_orders ro ON ro.id=rra.rental_order_id
        WHERE ro.status<>'CANCELLED' AND rr.return_date<=:end
              AND EXISTS (SELECT 1 FROM rental_return_items rri
                          WHERE rri.rental_return_id=rr.id)
        ORDER BY rr.return_date, rr.id""",
        {"end": end_date},
    )
    by_customer = {}
    for adj in adjustments:
        by_customer.setdefault(int(adj["customer_id"]), []).append(adj)
    return by_customer


def customer_balance_rows(end_date):
    """Outstanding balance for every customer as at ``end_date``.

    Rent is produced by the same charge engine the statement uses, so a customer's
    balance here always matches the closing balance on their statement. Charges are
    computed in Python rather than read from ``rental_charges``; that table is never
    written to, so joining it would report every customer's rent as zero.

    All the underlying data is loaded in a handful of queries and then grouped in
    memory, rather than running ``build_ledger`` once per customer.
    """
    customers = rows(
        """SELECT c.id AS customer_id, c.customer_code, c.customer_name, c.opening_balance
        FROM customers c ORDER BY c.customer_name""",
        {},
    )
    lines_by_customer = fetch_all_rental_lines(end_date)
    returns_by_line = fetch_all_line_returns(end_date)
    adjustments_by_customer = fetch_all_return_adjustments(end_date)

    payments = {
        int(r["customer_id"]): r["total"]
        for r in rows(
            """SELECT ro.customer_id, SUM(rp.amount) AS total
            FROM rental_payments rp
            JOIN rental_orders ro ON ro.id = rp.rental_order_id
            WHERE ro.status <> 'CANCELLED' AND rp.payment_date <= :end
            GROUP BY ro.customer_id""",
            {"end": end_date},
        )
    }
    manual = {
        int(r["customer_id"]): r
        for r in rows(
            """SELECT le.customer_id,
                   SUM(COALESCE(le.debit, 0)) AS debit_total,
                   SUM(COALESCE(le.credit, 0)) AS credit_total
            FROM ledger_entries le
            WHERE le.transaction_date <= :end
            GROUP BY le.customer_id""",
            {"end": end_date},
        )
    }
    orders = {
        int(r["customer_id"]): r
        for r in rows(
            """SELECT ro.customer_id,
                   SUM(CASE WHEN ro.status IN ('OPEN','PARTIALLY_RETURNED')
                            THEN 1 ELSE 0 END) AS open_orders,
                   MAX(ro.issue_date) AS last_activity
            FROM rental_orders ro
            WHERE ro.status <> 'CANCELLED' AND ro.issue_date <= :end
            GROUP BY ro.customer_id""",
            {"end": end_date},
        )
    }

    result = []
    for c in customers:
        cid = int(c["customer_id"])
        lines = lines_by_customer.get(cid, [])
        _timeline, calculations = collect_rental_events(lines, end_date, returns_by_line)
        adjustments = adjustments_by_customer.get(cid, [])
        discounts = compute_discounts(lines, calculations, adjustments)

        # Charge amounts already include GST where the bill opts in.
        rent = sum((money(x["amount"]) for x in calculations), ZERO)
        discount_total = sum((d["credit"] for d in discounts), ZERO)
        vehicle = sum(
            (money(a["vehicle_rent_amount"]) for a in adjustments), ZERO
        ) + sum(
            (
                money(line.get("vehicle_rent_amount"))
                for line in {
                    int(x["rental_order_id"]): x for x in lines if x.get("vehicle_rent_stage")
                }.values()
            ),
            ZERO,
        )
        order_row = orders.get(cid, {})
        result.append(
            {
                "customer_id": cid,
                "customer_code": c["customer_code"],
                "customer_name": c["customer_name"],
                "opening_balance": money(c["opening_balance"]),
                "charged_rent": rent,
                "discounts": discount_total,
                "vehicle_rent": vehicle,
                "payments": money(payments.get(cid, 0)),
                "manual_debits": money(manual.get(cid, {}).get("debit_total", 0)),
                "manual_credits": money(manual.get(cid, {}).get("credit_total", 0)),
                "open_orders": int(order_row.get("open_orders") or 0),
                "last_activity": order_row.get("last_activity"),
            }
        )
    return result


def summarise_balance(row):
    """Collapse one customer's totals into the figures the list screens show."""
    debits = row["charged_rent"] + row["vehicle_rent"] + row["manual_debits"]
    credits = row["payments"] + row["manual_credits"] + row["discounts"]
    balance = money(row["opening_balance"] + debits - credits)
    return {
        "customer_id": row["customer_id"],
        "customer_code": row["customer_code"],
        "customer_name": row["customer_name"],
        "opening_balance": float(row["opening_balance"]),
        "charged_rent": float(row["charged_rent"]),
        "discounts": float(row["discounts"]),
        "vehicle_rent": float(row["vehicle_rent"]),
        "payments": float(row["payments"]),
        "manual_debits": float(row["manual_debits"]),
        "manual_credits": float(row["manual_credits"]),
        "balance": float(balance),
        "open_orders": row["open_orders"],
        "last_activity": date_text(row["last_activity"]) if row["last_activity"] else None,
    }


def build_customer_history(customer_id, start=None, end=None):
    """Everything that happened with one customer: deliveries, returns, payments, balance.

    This reuses ``build_ledger`` so the balance here can never drift from the balance on
    the statement, then adds the delivery/return/payment detail the history screen shows.
    """
    ledger = build_ledger(customer_id, start, end)
    _start_date, end_date = resolve_period(start, end)

    deliveries = rows(
        """SELECT ro.id AS rental_order_id, ro.rental_number, ro.issue_date, ro.status,
               COALESCE(ro.site_name,'') AS site_name,
               COUNT(roi.id) AS line_count,
               COALESCE(SUM(roi.quantity_issued),0) AS total_issued
        FROM rental_orders ro
        LEFT JOIN rental_order_items roi ON roi.rental_order_id = ro.id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND ro.issue_date<=:end
        GROUP BY ro.id, ro.rental_number, ro.issue_date, ro.status, ro.site_name
        ORDER BY ro.issue_date DESC, ro.id DESC""",
        {"id": customer_id, "end": end_date},
    )
    for d in deliveries:
        d["issue_date"] = date_text(d["issue_date"])
        d["line_count"] = int(d["line_count"] or 0)
        d["total_issued"] = int(d["total_issued"] or 0)

    payments = rows(
        """SELECT rp.id, rp.payment_date, rp.amount, rp.payment_method, rp.payment_type,
               rp.reference_number, rp.notes, ro.rental_number
        FROM rental_payments rp
        JOIN rental_orders ro ON ro.id = rp.rental_order_id
        WHERE ro.customer_id=:id AND ro.status<>'CANCELLED' AND rp.payment_date<=:end
        ORDER BY rp.payment_date DESC, rp.id DESC""",
        {"id": customer_id, "end": end_date},
    )
    for p in payments:
        p["payment_date"] = date_text(p["payment_date"])
        p["amount"] = float(money(p["amount"]))

    return {
        "customer": ledger["customer"],
        "period_start": ledger["period_start"],
        "period_end": ledger["period_end"],
        "opening_balance": ledger["opening_balance"],
        "closing_balance": ledger["closing_balance"],
        "total_charged": ledger["total_charged"],
        "total_received": ledger["total_received"],
        "deliveries": deliveries,
        "payments": payments,
        "returns": ledger["return_history"],
        "running_items": ledger["running_items"],
        "bill_summaries": ledger["bill_summaries"],
        "entries": ledger["entries"],
    }


def download_response(payload, content_type, filename):
    resp = make_response(payload)
    resp.headers["Content-Type"] = content_type
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@blp.route("/balances")
class CustomerBalances(MethodView):
    """Outstanding balance for every customer, for the customer list screen."""

    @login_required
    @blp.response(200)
    def get(self):
        _start, end_date = resolve_period(None, request.args.get("end"))
        items = [summarise_balance(r) for r in customer_balance_rows(end_date)]
        return {
            "as_of": end_date.isoformat(),
            "items": items,
            "total_outstanding": float(sum((money(x["balance"]) for x in items), ZERO)),
        }


@blp.route("/customer/<int:customer_id>/history")
class CustomerHistory(MethodView):
    """Deliveries, returns, payments and balance for one customer."""

    @login_required
    @blp.response(200)
    def get(self, customer_id):
        return build_customer_history(
            customer_id, request.args.get("start"), request.args.get("end")
        )


@blp.route("/customer/<int:customer_id>")
class CustomerLedger(MethodView):
    @login_required
    @blp.response(200)
    def get(self, customer_id):
        return ledger_from_request(customer_id)


@blp.route("/customer/<int:customer_id>/excel")
class CustomerLedgerExcel(MethodView):
    @login_required
    def get(self, customer_id):
        data = ledger_from_request(customer_id)
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            abort(500, message="Install openpyxl to enable Excel export")

        buffer = BytesIO()
        build_statement_workbook(data).save(buffer)
        return download_response(
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            attachment_filename(data, customer_id, "xlsx"),
        )


@blp.route("/customer/<int:customer_id>/pdf")
class CustomerLedgerPdf(MethodView):
    @login_required
    def get(self, customer_id):
        data = ledger_from_request(customer_id)
        try:
            import reportlab  # noqa: F401
        except ImportError:
            abort(500, message="Install reportlab to enable PDF export")

        buffer = build_statement_pdf(data)
        return download_response(
            buffer.getvalue(),
            "application/pdf",
            attachment_filename(data, customer_id, "pdf"),
        )
