"""Operational reports.

Endpoints
---------
GET /api/reports/stock-availability - what is on hand vs out on rent
GET /api/reports/overdue            - deliveries still open past a day threshold
GET /api/reports/outstanding        - customers owing money, biggest first
GET /api/reports/revenue            - receipts per month
"""

from datetime import date, timedelta

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint

from ..security import login_required
from .ledgers import as_date, customer_balance_rows, money, rows, summarise_balance, ZERO

blp = Blueprint("reports", "reports", url_prefix="/api/reports", description="Operational reports")

# A delivery open longer than this is treated as overdue on the ageing report.
DEFAULT_OVERDUE_DAYS = 30
DEFAULT_REVENUE_MONTHS = 12


def as_of_date():
    raw = request.args.get("as_of")
    try:
        return date.fromisoformat(raw) if raw else date.today()
    except ValueError:
        return date.today()


@blp.route("/stock-availability")
class StockAvailability(MethodView):
    """Per item: total stock, how much is out on rent, and what is free."""

    @login_required
    @blp.response(200)
    def get(self):
        end = as_of_date()
        items = rows(
            """SELECT i.id, i.item_code, i.item_name, i.unit, i.total_stock,
                   COALESCE(out_.on_rent, 0) AS on_rent
            FROM items i
            LEFT JOIN (
                SELECT roi.item_id,
                       SUM(roi.quantity_issued) - COALESCE(SUM(ret.returned), 0) AS on_rent
                FROM rental_order_items roi
                JOIN rental_orders ro ON ro.id = roi.rental_order_id
                LEFT JOIN (
                    SELECT rri.rental_order_item_id, SUM(rri.quantity_returned) AS returned
                    FROM rental_return_items rri
                    JOIN rental_returns rr ON rr.id = rri.rental_return_id
                    WHERE rr.return_date <= :end
                    GROUP BY rri.rental_order_item_id
                ) ret ON ret.rental_order_item_id = roi.id
                WHERE ro.status <> 'CANCELLED' AND roi.issue_date <= :end
                GROUP BY roi.item_id
            ) out_ ON out_.item_id = i.id
            WHERE COALESCE(i.is_active, 1) = 1
            ORDER BY i.item_name""",
            {"end": end},
        )
        report = []
        for r in items:
            total = int(r["total_stock"] or 0)
            on_rent = max(int(r["on_rent"] or 0), 0)
            report.append(
                {
                    "item_code": r["item_code"],
                    "item_name": r["item_name"],
                    "unit": r["unit"],
                    "total_stock": total,
                    "on_rent": on_rent,
                    "available": total - on_rent,
                    # Flags items issued beyond recorded stock, which points at a data problem.
                    "oversubscribed": on_rent > total,
                }
            )
        return {
            "as_of": end.isoformat(),
            "items": report,
            "total_stock": sum(x["total_stock"] for x in report),
            "total_on_rent": sum(x["on_rent"] for x in report),
        }


@blp.route("/overdue")
class OverdueRentals(MethodView):
    """Deliveries still holding stock after the threshold, oldest first."""

    @login_required
    @blp.response(200)
    def get(self):
        end = as_of_date()
        try:
            threshold = max(int(request.args.get("days", DEFAULT_OVERDUE_DAYS)), 0)
        except ValueError:
            threshold = DEFAULT_OVERDUE_DAYS

        # The age cut-off is applied as a date so the SQL stays portable; DATEDIFF
        # and INTERVAL arithmetic are MySQL-specific.
        issued_on_or_before = end - timedelta(days=threshold)
        open_orders = rows(
            """SELECT ro.id, ro.rental_number, ro.issue_date, ro.status,
                   COALESCE(ro.site_name, '') AS site_name,
                   c.id AS customer_id, c.customer_name, c.phone,
                   SUM(roi.quantity_issued) - COALESCE(SUM(ret.returned), 0) AS outstanding_qty
            FROM rental_orders ro
            JOIN customers c ON c.id = ro.customer_id
            JOIN rental_order_items roi ON roi.rental_order_id = ro.id
            LEFT JOIN (
                SELECT rri.rental_order_item_id, SUM(rri.quantity_returned) AS returned
                FROM rental_return_items rri
                JOIN rental_returns rr ON rr.id = rri.rental_return_id
                WHERE rr.return_date <= :end
                GROUP BY rri.rental_order_item_id
            ) ret ON ret.rental_order_item_id = roi.id
            WHERE ro.status <> 'CANCELLED' AND ro.issue_date <= :cutoff
            GROUP BY ro.id, ro.rental_number, ro.issue_date, ro.status, ro.site_name,
                     c.id, c.customer_name, c.phone
            HAVING outstanding_qty > 0""",
            {"end": end, "cutoff": issued_on_or_before},
        )
        for o in open_orders:
            issued = as_date(o["issue_date"])
            o["issue_date"] = issued.isoformat() if issued else ""
            o["days_out"] = (end - issued).days if issued else 0
            o["outstanding_qty"] = int(o["outstanding_qty"] or 0)
            o["customer_id"] = int(o["customer_id"])
        open_orders.sort(key=lambda o: o["days_out"], reverse=True)
        return {"as_of": end.isoformat(), "threshold_days": threshold, "items": open_orders}


@blp.route("/outstanding")
class OutstandingBalances(MethodView):
    """Customers with money owing, largest balance first."""

    @login_required
    @blp.response(200)
    def get(self):
        end = as_of_date()
        balances = [summarise_balance(r) for r in customer_balance_rows(end)]
        owing = [b for b in balances if b["balance"] > 0]
        owing.sort(key=lambda b: b["balance"], reverse=True)
        return {
            "as_of": end.isoformat(),
            "items": owing,
            "total_outstanding": float(sum((money(b["balance"]) for b in owing), ZERO)),
            "customers_owing": len(owing),
        }


@blp.route("/revenue")
class RevenueReport(MethodView):
    """Receipts grouped by calendar month."""

    @login_required
    @blp.response(200)
    def get(self):
        end = as_of_date()
        try:
            months = max(min(int(request.args.get("months", DEFAULT_REVENUE_MONTHS)), 60), 1)
        except ValueError:
            months = DEFAULT_REVENUE_MONTHS

        # Window start and month bucketing are done in Python so the query avoids
        # DATE_SUB / DATE_FORMAT, which are MySQL-specific.
        start = end - timedelta(days=31 * months)
        payments = rows(
            """SELECT rp.payment_date, rp.amount
            FROM rental_payments rp
            JOIN rental_orders ro ON ro.id = rp.rental_order_id
            WHERE ro.status <> 'CANCELLED'
                  AND rp.payment_date <= :end AND rp.payment_date >= :start""",
            {"end": end, "start": start},
        )
        buckets: dict[str, dict[str, float]] = {}
        for p in payments:
            paid_on = as_date(p["payment_date"])
            if not paid_on:
                continue
            key = paid_on.strftime("%Y-%m")
            bucket = buckets.setdefault(key, {"received": 0.0, "payment_count": 0})
            bucket["received"] += float(money(p["amount"]))
            bucket["payment_count"] += 1
        series = [
            {
                "period": key,
                "received": round(b["received"], 2),
                "payment_count": int(b["payment_count"]),
            }
            for key, b in sorted(buckets.items())
        ]
        return {
            "as_of": end.isoformat(),
            "months": months,
            "items": series,
            "total_received": float(sum((money(s["received"]) for s in series), ZERO)),
        }
