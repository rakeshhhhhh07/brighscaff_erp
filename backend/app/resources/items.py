from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import or_
from .. import db
from ..models import Item
from ..schemas import ItemCreateSchema
from ..security import login_required

blp = Blueprint("items", "items", url_prefix="/api/items", description="Inventory catalogue")


@blp.route("/")
class ItemCollection(MethodView):
    @login_required
    @blp.response(200)
    def get(self):
        q = request.args.get("q", "").strip()
        query = Item.query
        if q:
            like = f"%{q}%"
            query = query.filter(or_(Item.item_name.ilike(like), Item.item_code.ilike(like)))
        return {"items": [i.to_dict() for i in query.order_by(Item.item_name.asc()).all()]}

    @login_required
    @blp.arguments(ItemCreateSchema)
    @blp.response(201)
    def post(self, data):
        if Item.query.filter_by(item_code=data["item_code"]).first():
            abort(409, message="Item code already exists")
        data["post_30_day_daily_rate"] = data.get("initial_daily_rate", 0)  # single daily rate
        obj = Item(**data)
        db.session.add(obj)
        db.session.commit()
        return obj.to_dict()


@blp.route("/<int:item_id>")
class ItemResource(MethodView):
    @login_required
    @blp.response(200)
    def get(self, item_id):
        obj = db.session.get(Item, item_id)
        if not obj:
            abort(404, message="Item not found")
        return obj.to_dict()

    @login_required
    @blp.arguments(ItemCreateSchema(partial=True))
    @blp.response(200)
    def put(self, data, item_id):
        obj = db.session.get(Item, item_id)
        if not obj:
            abort(404, message="Item not found")
        if "initial_daily_rate" in data:
            data["post_30_day_daily_rate"] = data["initial_daily_rate"]  # single daily rate
        for k, v in data.items():
            setattr(obj, k, v)
        db.session.commit()
        return obj.to_dict()

    @login_required
    def delete(self, item_id):
        """Safely deactivate instead of deleting inventory referenced by transactions."""
        obj = db.session.get(Item, item_id)
        if not obj:
            abort(404, message="Item not found")
        obj.is_active = False
        db.session.commit()
        return {
            "message": "Inventory item deactivated; historical stock and rental records were preserved.",
            "id": item_id,
        }
