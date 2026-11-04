"""Rental delivery, return and stock tracking endpoints.

Module layout
-------------
1. SQL statements       - every query kept as a named, readable constant.
2. Shared helpers       - row access, date coercion, order serialisation.
3. Delivery creation    - validation and insert steps for a new delivery bill.
4. Return recording     - validation and insert steps for a return.
5. Status / movements   - derived order status and inventory movement rebuilds.
6. Blueprint views      - thin HTTP layer delegating to the helpers above.

Stock rule: quantities are only returned to available stock when the condition is
GOOD. DAMAGED and MISSING stay charged against the delivery pending reconciliation.
"""

from datetime import date
from decimal import Decimal

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy import text

from .. import db
from ..security import login_required

blp = Blueprint(
    "rentals",
    "rentals",
    url_prefix="/api/rentals",
    description="Rental delivery, return and stock tracking",
)

VALID_CONDITIONS = ("GOOD", "DAMAGED", "MISSING")
DEFAULT_GST_RATE = 18


DISCOUNT_TYPES = ("PERCENT", "FIXED")


class RentalUpdateSchema(Schema):
    issue_date = fields.Date(allow_none=True)
    notes = fields.String(allow_none=True)
    site_name = fields.String(allow_none=True)


# ---------------------------------------------------------------------------
# 1. SQL statements
# ---------------------------------------------------------------------------

SQL_ORDER_WITH_CUSTOMER = """
    SELECT ro.*, c.customer_code, c.customer_name
    FROM rental_orders ro
    JOIN customers c ON c.id=ro.customer_id
    WHERE ro.id=:id
"""

SQL_ORDER_PAYMENTS = """
    SELECT id, payment_date, amount, payment_method, payment_type, reference_number, notes
    FROM rental_payments
    WHERE rental_order_id=:id
    ORDER BY payment_date, id
"""

SQL_ORDER_ITEMS = """
    SELECT roi.id AS rental_order_item_id, roi.item_id, i.item_code, i.item_name, i.unit,
           roi.quantity_issued, roi.initial_daily_rate, roi.post_30_day_daily_rate, roi.issue_date,
           COALESCE(roi.is_daily_rental,0) AS is_daily_rental,
           COALESCE((SELECT SUM(rri.quantity_returned) FROM rental_return_items rri
                     WHERE rri.rental_order_item_id=roi.id
                       AND rri.item_condition='GOOD'),0) AS quantity_returned_good,
           COALESCE((SELECT SUM(rri.quantity_returned) FROM rental_return_items rri
                     WHERE rri.rental_order_item_id=roi.id
                       AND rri.item_condition='DAMAGED'),0) AS quantity_damaged,
           COALESCE((SELECT SUM(rri.quantity_returned) FROM rental_return_items rri
                     WHERE rri.rental_order_item_id=roi.id
                       AND rri.item_condition='MISSING'),0) AS quantity_missing
    FROM rental_order_items roi
    JOIN items i ON i.id=roi.item_id
    WHERE roi.rental_order_id=:id
    ORDER BY roi.id
"""

SQL_ORDER_LIST = """
    SELECT ro.id, ro.rental_number, ro.customer_id, ro.issue_date, ro.status, ro.notes,
           ro.site_name, c.customer_code, c.customer_name,
           COUNT(DISTINCT roi.id) AS line_count,
           COALESCE(SUM(roi.quantity_issued),0) AS total_issued
    FROM rental_orders ro
    JOIN customers c ON c.id=ro.customer_id
    LEFT JOIN rental_order_items roi ON roi.rental_order_id=ro.id
    WHERE (:q='' OR ro.rental_number LIKE :like
           OR c.customer_name LIKE :like OR c.customer_code LIKE :like
           OR ro.site_name LIKE :like)
      AND (:status='' OR ro.status=:status)
    GROUP BY ro.id
    ORDER BY ro.issue_date DESC, ro.id DESC
"""

SQL_INSERT_ORDER = """
    INSERT INTO rental_orders
        (rental_number,customer_id,issue_date,status,notes,apply_gst,gst_rate,advance_paid,
         vehicle_rent_amount,vehicle_rent_stage,vehicle_type,vehicle_number,
         vehicle_paid_status,vehicle_payment_method,
         site_name,discount_allowed,discount_type,discount_value)
    VALUES(:num,:customer,:dt,'OPEN',:notes,:gst,:gstrate,:advance,:vehicle_amount,
           :vehicle_stage,:vehicle_type,:vehicle_number,:vehicle_status,:vehicle_method,
           :site,:disc_allowed,:disc_type,:disc_value)
"""

SQL_INSERT_ORDER_ITEM = """
    INSERT INTO rental_order_items
        (rental_order_id,item_id,quantity_issued,initial_daily_rate,
         post_30_day_daily_rate,issue_date,notes,is_daily_rental)
    VALUES(:oid,:iid,:qty,:rate,:post,:dt,:notes,:daily)
"""

SQL_INSERT_PAYMENT_ADVANCE = """
    INSERT INTO rental_payments
        (rental_order_id,payment_date,amount,payment_method,payment_type,reference_number,notes)
    VALUES(:oid,:dt,:amount,:method,'ADVANCE',:ref,:notes)
"""

SQL_INSERT_PAYMENT_RETURN = """
    INSERT INTO rental_payments
        (rental_order_id,payment_date,amount,payment_method,payment_type,reference_number,notes)
    VALUES(:oid,:dt,:amount,:method,'RETURN_PAYMENT',:ref,:notes)
"""

SQL_INSERT_PAYMENT_OTHER = """
    INSERT INTO rental_payments
        (rental_order_id,payment_date,amount,payment_method,payment_type,reference_number,notes)
    VALUES(:id,:dt,:amount,:method,'OTHER',:ref,:notes)
"""

SQL_INSERT_MOVEMENT_ISSUE = """
    INSERT INTO inventory_movements
        (item_id,movement_type,quantity,reference_type,reference_id,movement_date,notes)
    VALUES(:iid,'ISSUE',:qty,'RENTAL',:oid,:dt,:notes)
"""

SQL_INSERT_MOVEMENT_RETURN = """
    INSERT INTO inventory_movements
        (item_id,movement_type,quantity,reference_type,reference_id,movement_date,notes)
    VALUES(:iid,:type,:qty,'RETURN',:rid,:dt,:notes)
"""

# Issued-but-not-returned quantity for an item; only GOOD returns release stock.
SQL_ITEM_ON_RENT = """
    SELECT COALESCE((SELECT SUM(roi.quantity_issued)
                     FROM rental_order_items roi
                     JOIN rental_orders ro ON ro.id=roi.rental_order_id
                     WHERE roi.item_id=:id AND ro.status<>'CANCELLED'),0)
         - COALESCE((SELECT SUM(rri.quantity_returned)
                     FROM rental_return_items rri
                     JOIN rental_order_items roi ON roi.id=rri.rental_order_item_id
                     JOIN rental_orders ro ON ro.id=roi.rental_order_id
                     WHERE roi.item_id=:id AND rri.item_condition='GOOD'
                       AND ro.status<>'CANCELLED'),0)
"""

SQL_ACTIVE_ITEM_FOR_UPDATE = "SELECT * FROM items WHERE id=:id AND is_active=1 FOR UPDATE"
SQL_ACTIVE_CUSTOMER = "SELECT id FROM customers WHERE id=:id AND is_active=1"
SQL_NEXT_ORDER_ID = "SELECT COALESCE(MAX(id),0)+1 FROM rental_orders"
SQL_ORDER_BY_ID = "SELECT * FROM rental_orders WHERE id=:id"
SQL_ORDER_EXISTS = "SELECT id FROM rental_orders WHERE id=:id"
SQL_ACTIVE_ORDER_NUMBER = (
    "SELECT rental_number FROM rental_orders WHERE id=:id AND status<>'CANCELLED'"
)
SQL_ORDER_HAS_RETURNS = "SELECT rr.id FROM rental_returns rr WHERE rr.rental_order_id=:id LIMIT 1"
SQL_RETURN_COUNT = "SELECT COUNT(*)+1 FROM rental_returns WHERE rental_order_id=:id"

SQL_INSERT_RETURN = """
    INSERT INTO rental_returns(return_number,rental_order_id,return_date,notes)
    VALUES(:num,:oid,:dt,:notes)
"""

SQL_INSERT_RETURN_ITEM = """
    INSERT INTO rental_return_items
        (rental_return_id,rental_order_item_id,quantity_returned,item_condition,notes)
    VALUES(:rid,:oi,:qty,:cond,:notes)
"""

SQL_ISSUED_LINE = """
    SELECT roi.*, i.item_name, i.id AS item_id
    FROM rental_order_items roi
    JOIN items i ON i.id=roi.item_id
    WHERE roi.id=:id AND roi.rental_order_id=:oid
"""

SQL_LINE_RETURNED_TOTAL = """
    SELECT COALESCE(SUM(quantity_returned),0)
    FROM rental_return_items WHERE rental_order_item_id=:id
"""

SQL_LINE_RETURNED_OTHERS = """
    SELECT COALESCE(SUM(quantity_returned),0)
    FROM rental_return_items WHERE rental_order_item_id=:oi AND id<>:id
"""

SQL_ORDER_ISSUED_TOTAL = """
    SELECT COALESCE(SUM(quantity_issued),0)
    FROM rental_order_items WHERE rental_order_id=:id
"""

SQL_ORDER_RETURNED_TOTAL = """
    SELECT COALESCE(SUM(rri.quantity_returned),0)
    FROM rental_return_items rri
    JOIN rental_returns rr ON rr.id=rri.rental_return_id
    WHERE rr.rental_order_id=:id
"""

SQL_UPDATE_ORDER_STATUS = "UPDATE rental_orders SET status=:status WHERE id=:id"
SQL_UPDATE_ORDER_STATUS_IF_ACTIVE = (
    "UPDATE rental_orders SET status=:status WHERE id=:id AND status<>'CANCELLED'"
)
SQL_CANCEL_ORDER = "UPDATE rental_orders SET status='CANCELLED' WHERE id=:id"
SQL_UPDATE_ORDER_HEADER = (
    "UPDATE rental_orders SET issue_date=:dt, notes=:notes, site_name=:site WHERE id=:id"
)
SQL_UPDATE_ITEM_ISSUE_DATES = (
    "UPDATE rental_order_items SET issue_date=:dt WHERE rental_order_id=:id"
)

SQL_UPDATE_ORDER_VEHICLE = """
    UPDATE rental_orders
    SET vehicle_rent_amount=:amount, vehicle_rent_stage='RETURN',
        vehicle_type=:type, vehicle_number=:number
    WHERE id=:id
"""

SQL_RETURN_HISTORY = """
    SELECT rr.id AS return_id, rr.return_number, rr.return_date,
           DATE(rr.created_at) AS submitted_at, rr.notes AS return_notes,
           rri.id AS return_item_id, rri.rental_order_item_id, rri.quantity_returned,
           rri.item_condition, rri.notes,
           i.item_name, i.item_code, i.unit,
           rra.vehicle_rent_amount AS adj_vehicle_rent_amount,
           rra.vehicle_type AS adj_vehicle_type, rra.vehicle_number AS adj_vehicle_number,
           rra.discount_type AS adj_discount_type, rra.discount_value AS adj_discount_value
    FROM rental_returns rr
    LEFT JOIN rental_return_adjustments rra ON rra.rental_return_id=rr.id
    LEFT JOIN rental_return_items rri ON rri.rental_return_id=rr.id
    LEFT JOIN rental_order_items roi ON roi.id=rri.rental_order_item_id
    LEFT JOIN items i ON i.id=roi.item_id
    WHERE rr.rental_order_id=:id
    ORDER BY rr.return_date DESC, rr.id DESC, rri.id DESC
"""

SQL_RETURN_LINE_FOR_EDIT = """
    SELECT rri.*, rr.id AS header_id, rr.return_number, rr.return_date, rr.rental_order_id,
           roi.quantity_issued, roi.issue_date, roi.item_id
    FROM rental_return_items rri
    JOIN rental_returns rr ON rr.id=rri.rental_return_id
    JOIN rental_order_items roi ON roi.id=rri.rental_order_item_id
    WHERE rri.id=:id
"""

SQL_RETURN_LINE_FOR_DELETE = """
    SELECT rri.*, rr.id AS header_id, rr.return_number, rr.return_date,
           rr.notes AS header_notes, rr.rental_order_id
    FROM rental_return_items rri
    JOIN rental_returns rr ON rr.id=rri.rental_return_id
    WHERE rri.id=:id
"""

SQL_INSERT_RETURN_AUDIT = """
    INSERT INTO rental_return_audit
        (return_item_id,rental_return_id,action_type,old_return_number,old_return_date,
         old_rental_order_item_id,old_quantity_returned,old_item_condition,old_notes,reason)
    VALUES(:item,:header,:action,:num,:dt,:oi,:qty,:cond,:notes,:reason)
"""

SQL_RETURN_FOR_ADJUSTMENT = """
    SELECT rr.id, rr.rental_order_id, rr.return_number, ro.status AS order_status
    FROM rental_returns rr
    JOIN rental_orders ro ON ro.id=rr.rental_order_id
    WHERE rr.id=:id
"""

SQL_UPSERT_RETURN_ADJUSTMENT = """
    INSERT INTO rental_return_adjustments
        (rental_return_id,rental_order_id,vehicle_rent_amount,vehicle_type,vehicle_number,
         discount_type,discount_value)
    VALUES(:rid,:oid,:amount,:vtype,:vnumber,:dtype,:dvalue)
    ON DUPLICATE KEY UPDATE
        vehicle_rent_amount=VALUES(vehicle_rent_amount), vehicle_type=VALUES(vehicle_type),
        vehicle_number=VALUES(vehicle_number), discount_type=VALUES(discount_type),
        discount_value=VALUES(discount_value)
"""

SQL_DELETE_RETURN_ADJUSTMENT = "DELETE FROM rental_return_adjustments WHERE rental_return_id=:rid"

SQL_UPDATE_RETURN_DATE = "UPDATE rental_returns SET return_date=:dt WHERE id=:id"
SQL_UPDATE_RETURN_NOTES = "UPDATE rental_returns SET notes=:notes WHERE id=:id"
SQL_DELETE_RETURN_ITEM = "DELETE FROM rental_return_items WHERE id=:id"
SQL_UPDATE_RETURN_ITEM = """
    UPDATE rental_return_items
    SET quantity_returned=:qty, item_condition=:cond, notes=:notes
    WHERE id=:id
"""
SQL_RETURN_ITEM_COUNT = "SELECT COUNT(*) FROM rental_return_items WHERE rental_return_id=:id"
SQL_RETURN_HEADER = "SELECT return_number,return_date FROM rental_returns WHERE id=:id"
SQL_DELETE_RETURN_MOVEMENTS = (
    "DELETE FROM inventory_movements WHERE reference_type='RETURN' AND reference_id=:id"
)

SQL_RETURN_MOVEMENT_LINES = """
    SELECT roi.item_id, rri.quantity_returned, rri.item_condition, rri.notes
    FROM rental_return_items rri
    JOIN rental_order_items roi ON roi.id=rri.rental_order_item_id
    WHERE rri.rental_return_id=:id
"""

SQL_AUDIT_BY_RETURN = """
    SELECT * FROM rental_return_audit
    WHERE rental_return_id=:id ORDER BY changed_at DESC, id DESC
"""

SQL_AUDIT_BY_RETURN_ITEM = """
    SELECT * FROM rental_return_audit
    WHERE return_item_id=:id ORDER BY changed_at DESC, id DESC
"""


def _condition_totals_sql(condition=None):
    """Returned-quantity subquery per item, optionally restricted to one condition."""
    clause = f"AND rri.item_condition='{condition}' " if condition else ""
    return f"""COALESCE((SELECT SUM(rri.quantity_returned)
                FROM rental_return_items rri
                JOIN rental_order_items roi ON roi.id=rri.rental_order_item_id
                JOIN rental_orders ro ON ro.id=roi.rental_order_id
                WHERE roi.item_id=i.id {clause}AND ro.status<>'CANCELLED'),0)"""


SQL_STOCK = f"""
    SELECT i.id, i.item_code, i.item_name, i.unit, i.total_stock,
           COALESCE((SELECT SUM(roi.quantity_issued)
                     FROM rental_order_items roi
                     JOIN rental_orders ro ON ro.id=roi.rental_order_id
                     WHERE roi.item_id=i.id AND ro.status<>'CANCELLED'),0) AS issued,
           {_condition_totals_sql()} AS returned,
           {_condition_totals_sql('GOOD')} AS good_returned,
           {_condition_totals_sql('DAMAGED')} AS damaged,
           {_condition_totals_sql('MISSING')} AS missing
    FROM items i ORDER BY i.item_name
"""


# ---------------------------------------------------------------------------
# 2. Shared helpers
# ---------------------------------------------------------------------------


def rows(sql, params=None):
    return [dict(r._mapping) for r in db.session.execute(text(sql), params or {}).fetchall()]


def one(sql, params=None):
    r = db.session.execute(text(sql), params or {}).fetchone()
    return dict(r._mapping) if r else None


def scalar_int(sql, params=None):
    return int(db.session.execute(text(sql), params or {}).scalar() or 0)


def execute(sql, params=None):
    return db.session.execute(text(sql), params or {})


def iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def iso_day(value):
    """Date as YYYY-MM-DD, tolerating driver-dependent string/datetime results."""
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")[:10]


def parse_date(value, message):
    try:
        return date.fromisoformat(value)
    except Exception:
        abort(400, message=message)


def serialise_payment(payment):
    payment["payment_date"] = iso(payment["payment_date"])
    payment["amount"] = float(payment["amount"])
    return payment


def parse_discount(allowed, discount_type, value):
    """Validate a discount selection; returns ``(allowed, type, value)`` or raises ValueError."""
    if not allowed:
        return False, None, Decimal("0.00")
    kind = str(discount_type or "").upper()
    if kind not in DISCOUNT_TYPES:
        raise ValueError("Choose a discount type: percentage or fixed amount")
    try:
        amount = Decimal(str(value or 0))
    except Exception:
        raise ValueError("Enter a valid discount value")
    if amount <= 0:
        raise ValueError("Discount must be greater than zero")
    if kind == "PERCENT" and amount > 100:
        raise ValueError("Percentage discount cannot exceed 100")
    return True, kind, amount.quantize(Decimal("0.01"))


def serialise_order_item(item):
    item["issue_date"] = iso(item["issue_date"])
    item["initial_daily_rate"] = float(item["initial_daily_rate"])
    item["post_30_day_daily_rate"] = float(item["post_30_day_daily_rate"])
    item["is_daily_rental"] = bool(item.get("is_daily_rental"))
    item["quantity_returned_good"] = int(item["quantity_returned_good"])
    item["quantity_damaged"] = int(item["quantity_damaged"])
    item["quantity_missing"] = int(item["quantity_missing"])
    item["quantity_outstanding"] = (
        int(item["quantity_issued"])
        - item["quantity_returned_good"]
        - item["quantity_damaged"]
        - item["quantity_missing"]
    )
    return item


def order_detail(order_id):
    """Full delivery bill: header, payments and per-item outstanding quantities."""
    order = one(SQL_ORDER_WITH_CUSTOMER, {"id": order_id})
    if not order:
        return None
    order["issue_date"] = iso(order["issue_date"])
    order["created_at"] = iso(order["created_at"])
    order["discount_value"] = float(order.get("discount_value") or 0)
    order["discount_allowed"] = bool(order.get("discount_allowed"))
    order["payments"] = [serialise_payment(p) for p in rows(SQL_ORDER_PAYMENTS, {"id": order_id})]
    order["items"] = [serialise_order_item(i) for i in rows(SQL_ORDER_ITEMS, {"id": order_id})]
    return order


# ---------------------------------------------------------------------------
# 3. Delivery creation
# ---------------------------------------------------------------------------


def validate_delivery_request(data):
    """Validate the delivery payload and return the parsed issue date and lines."""
    customer_id = data.get("customer_id")
    issue_date = data.get("issue_date")
    lines = data.get("items") or []
    if not customer_id or not issue_date or not lines:
        abort(400, message="Customer, issue date and at least one item are required")
    issue = parse_date(issue_date, "Issue date must be YYYY-MM-DD")
    if not one(SQL_ACTIVE_CUSTOMER, {"id": customer_id}):
        abort(400, message="Select an active customer")
    return customer_id, issue, lines


def next_rental_number(data):
    if data.get("rental_number"):
        return data["rental_number"]
    return f"DC-{date.today():%Y%m%d}-{scalar_int(SQL_NEXT_ORDER_ID):05d}"


def insert_delivery_order(data, num, customer_id, issue):
    disc_allowed, disc_type, disc_value = parse_discount(
        data.get("discount_allowed"), data.get("discount_type"), data.get("discount_value")
    )
    site_name = (data.get("site_name") or "").strip() or None
    result = execute(
        SQL_INSERT_ORDER,
        {
            "num": num,
            "customer": customer_id,
            "dt": issue,
            "notes": data.get("notes"),
            "gst": bool(data.get("apply_gst")),
            "gstrate": data.get("gst_rate") or DEFAULT_GST_RATE,
            "advance": data.get("advance_paid") or 0,
            "vehicle_amount": data.get("vehicle_rent_amount") or 0,
            "vehicle_stage": data.get("vehicle_rent_stage"),
            "vehicle_type": data.get("vehicle_type"),
            "vehicle_number": data.get("vehicle_number"),
            "vehicle_status": data.get("vehicle_paid_status") or "UNPAID",
            "vehicle_method": data.get("vehicle_payment_method"),
            "site": site_name,
            "disc_allowed": disc_allowed,
            "disc_type": disc_type,
            "disc_value": disc_value,
        },
    )
    return result.lastrowid


def record_advance_payment(data, order_id, num, issue):
    amount = Decimal(str(data.get("advance_paid") or 0))
    if amount < 0:
        raise ValueError("Advance payment cannot be negative")
    if amount == 0:
        return
    execute(
        SQL_INSERT_PAYMENT_ADVANCE,
        {
            "oid": order_id,
            "dt": issue,
            "amount": amount,
            "method": data.get("advance_payment_method"),
            "ref": num,
            "notes": "Advance received at delivery",
        },
    )


def issue_delivery_line(line, order_id, num, issue):
    """Validate stock for one requested line, then write the item and its movement."""
    item_id = int(line.get("item_id") or 0)
    qty = int(line.get("quantity") or 0)
    if qty < 1:
        raise ValueError("Each issue quantity must be at least 1")
    item = one(SQL_ACTIVE_ITEM_FOR_UPDATE, {"id": item_id})
    if not item:
        raise ValueError(f"Item {item_id} not found or inactive")

    # Stock is enforced against all quantities not yet returned,
    # including damaged/missing pending reconciliation.
    on_rent = scalar_int(SQL_ITEM_ON_RENT, {"id": item_id})
    available = int(item["total_stock"]) - on_rent
    if qty > available:
        raise ValueError(
            f"Insufficient available stock for {item['item_name']}. Available: {max(0, available)}"
        )

    execute(
        SQL_INSERT_ORDER_ITEM,
        {
            "oid": order_id,
            "iid": item_id,
            "qty": qty,
            "rate": item["initial_daily_rate"],
            # One daily rate only: keep the legacy "after 30 days" column identical.
            "post": item["initial_daily_rate"],
            "dt": issue,
            "notes": line.get("notes"),
            "daily": bool(line.get("is_daily_rental")),
        },
    )
    execute(
        SQL_INSERT_MOVEMENT_ISSUE,
        {"iid": item_id, "qty": -qty, "oid": order_id, "dt": issue, "notes": num},
    )


def create_delivery(data, customer_id, issue, lines):
    """Write the delivery bill, its advance payment and all issued lines."""
    num = next_rental_number(data)
    order_id = insert_delivery_order(data, num, customer_id, issue)
    record_advance_payment(data, order_id, num, issue)
    for line in lines:
        issue_delivery_line(line, order_id, num, issue)
    return order_id


# ---------------------------------------------------------------------------
# 4. Return recording
# ---------------------------------------------------------------------------


def validate_return_request(data, order_id):
    """Validate the return payload against the delivery bill."""
    dt = data.get("return_date")
    lines = data.get("items") or []
    if not dt or not lines:
        abort(400, message="Return date and at least one return line are required")
    return_date = parse_date(dt, "Return date must be YYYY-MM-DD")
    order = one(SQL_ORDER_BY_ID, {"id": order_id})
    if not order:
        abort(404, message="Rental delivery not found")
    if return_date < order["issue_date"]:
        abort(400, message="Return date cannot be before the delivery date")
    return return_date, lines


def next_return_number(data, order_id):
    if data.get("return_number"):
        return data["return_number"]
    sequence = scalar_int(SQL_RETURN_COUNT, {"id": order_id})
    return f"RC-{date.today():%Y%m%d}-{order_id:05d}-{sequence:02d}"


def movement_type_for(condition):
    """GOOD restores stock; DAMAGED and MISSING are tracked but not restored."""
    if condition == "GOOD":
        return "RETURN"
    return "DAMAGE" if condition == "DAMAGED" else "LOSS"


def record_return_line(line, order_id, return_id, retno, return_date):
    """Validate one return line against its delivery line, then write it."""
    oi = int(line.get("rental_order_item_id") or 0)
    qty = int(line.get("quantity") or 0)
    cond = line.get("condition", "GOOD").upper()
    if qty < 1 or cond not in VALID_CONDITIONS:
        raise ValueError(
            "Return quantity must be positive and condition must be GOOD, DAMAGED or MISSING"
        )
    issued = one(SQL_ISSUED_LINE, {"id": oi, "oid": order_id})
    if not issued:
        raise ValueError("A selected item does not belong to this delivery")
    already = scalar_int(SQL_LINE_RETURNED_TOTAL, {"id": oi})
    if qty > int(issued["quantity_issued"]) - already:
        raise ValueError(f"Return quantity exceeds outstanding quantity for {issued['item_name']}")

    execute(
        SQL_INSERT_RETURN_ITEM,
        {"rid": return_id, "oi": oi, "qty": qty, "cond": cond, "notes": line.get("notes")},
    )
    # Damaged/missing are not returned to available stock; GOOD is.
    execute(
        SQL_INSERT_MOVEMENT_RETURN,
        {
            "iid": issued["item_id"],
            "type": movement_type_for(cond),
            "qty": qty if cond == "GOOD" else 0,
            "rid": return_id,
            "dt": return_date,
            "notes": f"{retno}: {cond}",
        },
    )


def status_after_return(order_id):
    """Any recorded returned condition closes the rental quantity;
    damaged/missing are separately accounted."""
    allqty = scalar_int(SQL_ORDER_ISSUED_TOTAL, {"id": order_id})
    returnedqty = scalar_int(SQL_ORDER_RETURNED_TOTAL, {"id": order_id})
    remaining = allqty - returnedqty
    if remaining <= 0:
        return "CLOSED"
    return "PARTIALLY_RETURNED" if remaining < allqty else "OPEN"


def record_return_vehicle_rent(data, order_id):
    amount = Decimal(str(data.get("vehicle_rent_amount") or 0))
    if amount < 0:
        raise ValueError("Vehicle rent cannot be negative")
    if amount == 0:
        return
    execute(
        SQL_UPDATE_ORDER_VEHICLE,
        {
            "amount": amount,
            "type": data.get("vehicle_type"),
            "number": data.get("vehicle_number"),
            "id": order_id,
        },
    )


def record_return_payment(data, order_id, retno, return_date):
    paid = Decimal(str(data.get("payment_amount") or 0))
    if paid < 0:
        raise ValueError("Payment amount cannot be negative")
    if paid == 0:
        return
    execute(
        SQL_INSERT_PAYMENT_RETURN,
        {
            "oid": order_id,
            "dt": return_date,
            "amount": paid,
            "method": data.get("payment_method"),
            "ref": retno,
            "notes": data.get("payment_notes") or "Payment received at return",
        },
    )


def create_return(data, order_id, return_date, lines):
    """Write the return header, its lines, vehicle rent, payment and new order status."""
    retno = next_return_number(data, order_id)
    result = execute(
        SQL_INSERT_RETURN,
        {"num": retno, "oid": order_id, "dt": return_date, "notes": data.get("notes")},
    )
    return_id = result.lastrowid
    for line in lines:
        record_return_line(line, order_id, return_id, retno, return_date)

    status = status_after_return(order_id)
    record_return_vehicle_rent(data, order_id)
    record_return_payment(data, order_id, retno, return_date)
    execute(SQL_UPDATE_ORDER_STATUS, {"status": status, "id": order_id})
    return retno


# ---------------------------------------------------------------------------
# 5. Status / movements
# ---------------------------------------------------------------------------


def refresh_order_status(order_id):
    allqty = scalar_int(SQL_ORDER_ISSUED_TOTAL, {"id": order_id})
    retqty = scalar_int(SQL_ORDER_RETURNED_TOTAL, {"id": order_id})
    if retqty >= allqty and allqty > 0:
        status = "CLOSED"
    else:
        status = "PARTIALLY_RETURNED" if retqty > 0 else "OPEN"
    execute(SQL_UPDATE_ORDER_STATUS_IF_ACTIVE, {"status": status, "id": order_id})


def rebuild_return_movements(return_id):
    """Rebuild movements for this return header from its surviving detail lines."""
    execute(SQL_DELETE_RETURN_MOVEMENTS, {"id": return_id})
    head = one(SQL_RETURN_HEADER, {"id": return_id})
    if not head:
        return
    for line in rows(SQL_RETURN_MOVEMENT_LINES, {"id": return_id}):
        cond = line["item_condition"]
        execute(
            SQL_INSERT_MOVEMENT_RETURN,
            {
                "iid": line["item_id"],
                "type": movement_type_for(cond),
                "qty": line["quantity_returned"] if cond == "GOOD" else 0,
                "rid": return_id,
                "dt": head["return_date"],
                "notes": f"{head['return_number']}: {cond}",
            },
        )


def write_return_audit(action, current, reason, return_item_id):
    """Preserve the pre-change values of a return line before editing or deleting it."""
    execute(
        SQL_INSERT_RETURN_AUDIT,
        {
            "item": return_item_id,
            "header": current["header_id"],
            "action": action,
            "num": current["return_number"],
            "dt": current["return_date"],
            "oi": current["rental_order_item_id"],
            "qty": current["quantity_returned"],
            "cond": current["item_condition"],
            "notes": current["notes"],
            "reason": reason,
        },
    )


def require_reason(data, message):
    reason = (data.get("reason") or "").strip()
    if not reason:
        abort(400, message=message)
    return reason


# ---------------------------------------------------------------------------
# 6. Blueprint views
# ---------------------------------------------------------------------------


@blp.route("/")
class RentalCollection(MethodView):
    @login_required
    @blp.response(200)
    def get(self):
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "")
        data = rows(SQL_ORDER_LIST, {"q": q, "like": f"%{q}%", "status": status})
        for r in data:
            r["issue_date"] = iso(r["issue_date"])
        return {"items": data}

    @login_required
    @blp.response(201)
    def post(self):
        data = request.get_json(silent=True) or {}
        customer_id, issue, lines = validate_delivery_request(data)
        db.session.commit()
        try:
            with db.session.begin():
                order_id = create_delivery(data, customer_id, issue, lines)
            return order_detail(order_id)
        except ValueError as e:
            db.session.rollback()
            abort(400, message=str(e))
        except Exception:
            db.session.rollback()
            raise


@blp.route("/<int:order_id>")
class RentalResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, order_id):
        data = order_detail(order_id)
        if not data:
            abort(404, message="Rental delivery not found")
        return data

    @login_required
    @blp.arguments(RentalUpdateSchema(partial=True))
    @blp.response(200)
    def put(self, data, order_id):
        order = one(SQL_ORDER_BY_ID, {"id": order_id})
        if not order:
            abort(404, message="Rental delivery not found")
        if order["status"] == "CANCELLED":
            abort(400, message="Cancelled delivery bills cannot be edited")

        new_date = order["issue_date"]
        if data.get("issue_date"):
            new_date = data["issue_date"]
            if new_date != order["issue_date"] and one(SQL_ORDER_HAS_RETURNS, {"id": order_id}):
                abort(
                    400,
                    message=(
                        "Issue date cannot be changed after returns exist; "
                        "edit notes only to preserve the timeline"
                    ),
                )

        execute(
            SQL_UPDATE_ORDER_HEADER,
            {
                "dt": new_date,
                "notes": data.get("notes", order.get("notes")),
                "site": (
                    (data.get("site_name") or "").strip() or None
                    if "site_name" in data
                    else order.get("site_name")
                ),
                "id": order_id,
            },
        )
        if data.get("issue_date"):
            execute(SQL_UPDATE_ITEM_ISSUE_DATES, {"dt": new_date, "id": order_id})
        db.session.commit()
        return order_detail(order_id)

    @login_required
    @blp.response(200)
    def delete(self, order_id):
        order = one(SQL_ORDER_BY_ID, {"id": order_id})
        if not order:
            abort(404, message="Rental delivery not found")
        if order["status"] == "CANCELLED":
            return {"message": "Delivery bill is already cancelled"}
        if one(SQL_ORDER_HAS_RETURNS, {"id": order_id}):
            abort(
                409,
                message=(
                    "This bill has return history. It cannot be deleted; "
                    "keep the timeline and contact support for a correction."
                ),
            )
        execute(SQL_CANCEL_ORDER, {"id": order_id})
        db.session.commit()
        return {"message": "Delivery bill cancelled. The record is retained for audit history."}


@blp.route("/<int:order_id>/payments")
class RentalPaymentsResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, order_id):
        if not one(SQL_ORDER_EXISTS, {"id": order_id}):
            abort(404, message="Delivery bill not found")
        return {"items": rows(SQL_ORDER_PAYMENTS, {"id": order_id})}

    @login_required
    @blp.response(201)
    def post(self, order_id):
        data = request.get_json(silent=True) or {}
        try:
            dt = date.fromisoformat(data.get("payment_date") or date.today().isoformat())
            amount = Decimal(str(data.get("amount") or 0))
        except Exception:
            abort(400, message="Enter a valid payment date and amount")
        if amount <= 0:
            abort(400, message="Payment amount must be greater than zero")
        order = one(SQL_ACTIVE_ORDER_NUMBER, {"id": order_id})
        if not order:
            abort(404, message="Active delivery bill not found")

        result = execute(
            SQL_INSERT_PAYMENT_OTHER,
            {
                "id": order_id,
                "dt": dt,
                "amount": amount,
                "method": data.get("payment_method"),
                "ref": data.get("reference_number") or order["rental_number"],
                "notes": data.get("notes"),
            },
        )
        db.session.commit()
        return {
            "id": result.lastrowid,
            "message": "Payment recorded",
            "payment": {
                "amount": float(amount),
                "payment_date": dt.isoformat(),
                "payment_method": data.get("payment_method"),
            },
        }


@blp.route("/<int:order_id>/returns")
class ReturnCollection(MethodView):
    @login_required
    @blp.response(201)
    def post(self, order_id):
        data = request.get_json(silent=True) or {}
        return_date, lines = validate_return_request(data, order_id)
        db.session.commit()
        try:
            with db.session.begin():
                retno = create_return(data, order_id, return_date, lines)
            return {"return_number": retno, "rental": order_detail(order_id)}
        except ValueError as e:
            db.session.rollback()
            abort(400, message=str(e))


@blp.route("/<int:order_id>/returns")
class ReturnHistoryResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, order_id):
        if not one(SQL_ORDER_EXISTS, {"id": order_id}):
            abort(404, message="Rental delivery not found")
        items = rows(SQL_RETURN_HISTORY, {"id": order_id})
        for item in items:
            item["return_date"] = iso_day(item.get("return_date"))
            item["submitted_at"] = iso_day(item.get("submitted_at"))
            item["adj_vehicle_rent_amount"] = float(item.get("adj_vehicle_rent_amount") or 0)
            item["adj_discount_value"] = float(item.get("adj_discount_value") or 0)
        return {"items": items}


@blp.route("/return-items/<int:return_item_id>")
class ReturnItemCorrectionResource(MethodView):
    @login_required
    @blp.response(200)
    def put(self, return_item_id):
        data = request.get_json(silent=True) or {}
        reason = require_reason(data, "A correction reason is required for audit history")
        current = one(SQL_RETURN_LINE_FOR_EDIT, {"id": return_item_id})
        if not current:
            abort(404, message="Return line not found (it may already have been deleted)")

        qty = int(data.get("quantity_returned", current["quantity_returned"]))
        cond = str(data.get("item_condition", current["item_condition"])).upper()
        notes = data.get("notes", current["notes"])
        new_date = (
            date.fromisoformat(data["return_date"])
            if data.get("return_date")
            else current["return_date"]
        )
        if qty < 1 or cond not in VALID_CONDITIONS:
            abort(
                400,
                message="Quantity must be positive and condition must be GOOD, DAMAGED or MISSING",
            )
        if new_date < current["issue_date"]:
            abort(400, message="Return date cannot be before delivery date")

        other = scalar_int(
            SQL_LINE_RETURNED_OTHERS,
            {"oi": current["rental_order_item_id"], "id": return_item_id},
        )
        if qty > int(current["quantity_issued"]) - other:
            abort(
                400,
                message="Corrected quantity exceeds the outstanding quantity for this delivery line",
            )

        write_return_audit("EDIT", current, reason, return_item_id)
        execute(SQL_UPDATE_RETURN_DATE, {"dt": new_date, "id": current["header_id"]})
        execute(
            SQL_UPDATE_RETURN_ITEM,
            {"qty": qty, "cond": cond, "notes": notes, "id": return_item_id},
        )
        rebuild_return_movements(current["header_id"])
        refresh_order_status(current["rental_order_id"])
        db.session.commit()
        return {
            "message": "Return line corrected; previous values retained in audit history.",
            "return_item_id": return_item_id,
        }

    @login_required
    @blp.response(200)
    def delete(self, return_item_id):
        data = request.get_json(silent=True) or {}
        reason = require_reason(data, "A deletion reason is required for audit history")
        current = one(SQL_RETURN_LINE_FOR_DELETE, {"id": return_item_id})
        if not current:
            abort(404, message="Return line not found (it may already have been deleted)")

        write_return_audit("DELETE", current, reason, return_item_id)
        execute(SQL_DELETE_RETURN_ITEM, {"id": return_item_id})

        remaining = scalar_int(SQL_RETURN_ITEM_COUNT, {"id": current["header_id"]})
        if remaining == 0:
            oldnotes = current.get("header_notes") or ""
            voided = oldnotes + " | VOIDED: all return lines removed through audited correction"
            execute(
                SQL_UPDATE_RETURN_NOTES,
                {"notes": voided.strip(" |"), "id": current["header_id"]},
            )

        rebuild_return_movements(current["header_id"])
        refresh_order_status(current["rental_order_id"])
        db.session.commit()
        return {
            "message": (
                "Return line deleted. Original values and reason are preserved "
                "in rental_return_audit."
            )
        }


@blp.route("/returns/<int:return_id>/adjustments")
class ReturnAdjustmentResource(MethodView):
    """Vehicle rent and/or discount attached to one return bill (from Return history)."""

    @login_required
    @blp.response(200)
    def put(self, return_id):
        data = request.get_json(silent=True) or {}
        ret = one(SQL_RETURN_FOR_ADJUSTMENT, {"id": return_id})
        if not ret:
            abort(404, message="Return bill not found")
        if ret["order_status"] == "CANCELLED":
            abort(400, message="Cancelled delivery bills cannot be changed")

        try:
            amount = Decimal(str(data.get("vehicle_rent_amount") or 0))
            if amount < 0:
                raise ValueError("Vehicle rent cannot be negative")
            discount_value = Decimal(str(data.get("discount_value") or 0))
            has_discount = discount_value > 0
            _allowed, kind, value = parse_discount(
                has_discount, data.get("discount_type"), discount_value
            )
        except ValueError as e:
            abort(400, message=str(e))
        except Exception:
            abort(400, message="Enter valid vehicle rent and discount values")

        if amount == 0 and not has_discount:
            execute(SQL_DELETE_RETURN_ADJUSTMENT, {"rid": return_id})
            db.session.commit()
            return {"message": "Vehicle rent and discount removed for this return."}

        execute(
            SQL_UPSERT_RETURN_ADJUSTMENT,
            {
                "rid": return_id,
                "oid": ret["rental_order_id"],
                "amount": amount,
                "vtype": (data.get("vehicle_type") or "").strip() or None,
                "vnumber": (data.get("vehicle_number") or "").strip() or None,
                "dtype": kind,
                "dvalue": value,
            },
        )
        db.session.commit()
        return {"message": "Vehicle rent and discount saved; the statement now includes them."}


@blp.route("/returns/<int:return_id>/audit")
class ReturnHeaderAuditResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, return_id):
        return {"items": rows(SQL_AUDIT_BY_RETURN, {"id": return_id})}


@blp.route("/return-items/<int:return_item_id>/audit")
class ReturnItemAuditResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, return_item_id):
        return {"items": rows(SQL_AUDIT_BY_RETURN_ITEM, {"id": return_item_id})}


@blp.route("/stock")
class StockResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self):
        data = rows(SQL_STOCK)
        for r in data:
            r["issued"] = int(r["issued"] or 0)
            r["returned"] = int(r["returned"] or 0)
            r["good_returned"] = int(r["good_returned"] or 0)
            r["damaged"] = int(r["damaged"] or 0)
            r["missing"] = int(r["missing"] or 0)
            r["on_rent"] = max(0, r["issued"] - r["returned"])
            r["available_stock"] = max(0, int(r["total_stock"]) - r["issued"] + r["good_returned"])
        return {"items": data}
