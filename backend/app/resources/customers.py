from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import or_
from .. import db
from ..models import Customer
from ..schemas import CustomerCreateSchema
from ..security import login_required

blp = Blueprint(
    "customers", "customers", url_prefix="/api/customers", description="Customer management"
)


@blp.route("/")
class CustomerCollection(MethodView):
    @login_required
    @blp.response(200)
    def get(self):
        q = request.args.get("q", "").strip()
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
        query = Customer.query
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    Customer.customer_name.ilike(like),
                    Customer.customer_code.ilike(like),
                    Customer.phone.ilike(like),
                )
            )
        p = query.order_by(Customer.customer_name.asc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            "items": [c.to_dict() for c in p.items],
            "page": page,
            "per_page": per_page,
            "total": p.total,
            "pages": p.pages,
        }

    @login_required
    @blp.arguments(CustomerCreateSchema)
    @blp.response(201)
    def post(self, data):
        if Customer.query.filter_by(customer_code=data["customer_code"]).first():
            abort(409, message="Customer code already exists")
        obj = Customer(**data)
        db.session.add(obj)
        db.session.commit()
        return obj.to_dict()


@blp.route("/<int:customer_id>")
class CustomerResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, customer_id):
        obj = db.session.get(Customer, customer_id)
        if not obj:
            abort(404, message="Customer not found")
        return obj.to_dict()

    @login_required
    @blp.arguments(CustomerCreateSchema(partial=True))
    @blp.response(200)
    def put(self, data, customer_id):
        obj = db.session.get(Customer, customer_id)
        if not obj:
            abort(404, message="Customer not found")
        for k, v in data.items():
            setattr(obj, k, v)
        db.session.commit()
        return obj.to_dict()

    @login_required
    def delete(self, customer_id):
        """Safely deactivate instead of physically deleting referenced customer history."""
        obj = db.session.get(Customer, customer_id)
        if not obj:
            abort(404, message="Customer not found")
        obj.is_active = False
        db.session.commit()
        return {
            "message": "Customer deactivated; historical rental and ledger records were preserved.",
            "id": customer_id,
        }


@blp.route("/import")
class CustomerImport(MethodView):
    @login_required
    @blp.response(201)
    def post(self):
        payload = request.get_json(silent=True) or {}
        rows = payload.get("customers", [])
        if not isinstance(rows, list):
            abort(400, message="customers must be a list")
        created = []
        skipped = 0
        for row in rows:
            if (
                not isinstance(row, dict)
                or not str(row.get("customer_code", "")).strip()
                or not str(row.get("customer_name", "")).strip()
            ):
                skipped += 1
                continue
            code = str(row["customer_code"]).strip()
            if Customer.query.filter_by(customer_code=code).first():
                skipped += 1
                continue
            try:
                obj = Customer(
                    customer_code=code,
                    customer_name=str(row["customer_name"]).strip(),
                    contact_person=(str(row.get("contact_person") or "").strip() or None),
                    phone=(str(row.get("phone") or "").strip() or None),
                    email=(str(row.get("email") or "").strip() or None),
                    billing_address=(str(row.get("billing_address") or "").strip() or None),
                    site_address=(str(row.get("site_address") or "").strip() or None),
                    tax_number=(str(row.get("tax_number") or "").strip() or None),
                    opening_balance=row.get("opening_balance") or 0,
                )
                db.session.add(obj)
                db.session.flush()
                created.append(obj)
            except Exception:
                db.session.rollback()
                abort(400, message=f"Invalid customer data for code {code}")
        db.session.commit()
        return {"created": [c.to_dict() for c in created], "skipped": skipped}
