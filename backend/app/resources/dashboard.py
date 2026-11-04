from flask_smorest import Blueprint
from sqlalchemy import func, text

from .. import db
from ..models import Customer, Item
from ..security import login_required

blp = Blueprint(
    "dashboard", "dashboard", url_prefix="/api/dashboard", description="Dashboard summaries"
)

SQL_ACTIVE_RENTALS = """
    SELECT COUNT(*) FROM rental_orders
    WHERE status IN ('OPEN','PARTIALLY_RETURNED')
"""

# Quantities still with customers: everything issued, less everything returned.
SQL_ITEMS_ON_RENT = """
    SELECT COALESCE(SUM(x.issued_qty - x.returned_qty),0)
    FROM (
        SELECT roi.id,
               roi.quantity_issued AS issued_qty,
               COALESCE((SELECT SUM(rri.quantity_returned)
                         FROM rental_return_items rri
                         WHERE rri.rental_order_item_id=roi.id),0) AS returned_qty
        FROM rental_order_items roi
        JOIN rental_orders ro ON ro.id=roi.rental_order_id
        WHERE ro.status<>'CANCELLED'
    ) x
"""

def scalar_int(sql):
    return int(db.session.execute(text(sql)).scalar() or 0)


def outstanding_total():
    """Total owed across all customers, from the same aggregate the customer list uses.

    Returns ``(amount, customers_owing)``. Falls back to zero when the billing tables
    have not been migrated yet, so the dashboard still renders on a partial database.
    """
    from datetime import date

    from .ledgers import customer_balance_rows, summarise_balance

    try:
        balances = [summarise_balance(r) for r in customer_balance_rows(date.today())]
    except Exception:
        db.session.rollback()
        return 0.0, 0
    owing = [b["balance"] for b in balances if b["balance"] > 0]
    return round(sum(owing), 2), len(owing)


@blp.route("/summary")
@login_required
def summary():
    total_stock = int(db.session.query(func.coalesce(func.sum(Item.total_stock), 0)).scalar() or 0)
    outstanding, customers_owing = outstanding_total()
    return {
        "customers": Customer.query.count(),
        "active_customers": Customer.query.filter_by(is_active=True).count(),
        "catalogue_items": Item.query.count(),
        "total_stock": total_stock,
        "active_rentals": scalar_int(SQL_ACTIVE_RENTALS),
        "items_on_rent": max(0, scalar_int(SQL_ITEMS_ON_RENT)),
        "rent_accrued": 0,
        "outstanding_amount": outstanding,
        "customers_owing": customers_owing,
    }
