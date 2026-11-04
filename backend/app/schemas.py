from marshmallow import Schema, fields, validate


class CustomerCreateSchema(Schema):
    customer_code = fields.String(required=True, validate=validate.Length(min=1, max=40))
    customer_name = fields.String(required=True, validate=validate.Length(min=1, max=180))
    contact_person = fields.String(allow_none=True)
    phone = fields.String(allow_none=True)
    email = fields.Email(allow_none=True)
    billing_address = fields.String(allow_none=True)
    site_address = fields.String(allow_none=True)
    tax_number = fields.String(allow_none=True)
    company = fields.String(allow_none=True)
    main_mobile = fields.String(allow_none=True)
    mobile_2 = fields.String(allow_none=True)
    mobile_3 = fields.String(allow_none=True)
    office_address = fields.String(allow_none=True)
    office_email = fields.Email(allow_none=True)
    residential_address = fields.String(allow_none=True)
    gst_number = fields.String(allow_none=True)
    guarantor_relationship = fields.String(allow_none=True)
    guarantor_name = fields.String(allow_none=True)
    guarantor_contact = fields.String(allow_none=True)
    guarantor_address = fields.String(allow_none=True)
    opening_balance = fields.Decimal(as_string=True, load_default="0.00")
    is_active = fields.Boolean(load_default=True)


class ItemCreateSchema(Schema):
    item_code = fields.String(required=True, validate=validate.Length(min=1, max=50))
    item_name = fields.String(required=True, validate=validate.Length(min=1, max=180))
    category = fields.String(allow_none=True)
    unit = fields.String(load_default="Nos")
    total_stock = fields.Integer(load_default=0, validate=validate.Range(min=0))
    initial_daily_rate = fields.Decimal(
        as_string=True, load_default="0.00", validate=validate.Range(min=0)
    )
    post_30_day_daily_rate = fields.Decimal(
        as_string=True, load_default="0.00", validate=validate.Range(min=0)
    )
    has_monthly_minimum = fields.Boolean(load_default=True)
    is_active = fields.Boolean(load_default=True)
