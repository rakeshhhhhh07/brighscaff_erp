from datetime import datetime
from . import db


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.BigInteger, primary_key=True)
    customer_code = db.Column(db.String(40), unique=True, nullable=False)
    customer_name = db.Column(db.String(180), nullable=False)
    contact_person = db.Column(db.String(180))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(180))
    company = db.Column(db.String(180))
    main_mobile = db.Column(db.String(40))
    mobile_2 = db.Column(db.String(40))
    mobile_3 = db.Column(db.String(40))
    office_address = db.Column(db.Text)
    office_email = db.Column(db.String(180))
    residential_address = db.Column(db.Text)
    gst_number = db.Column(db.String(80))
    guarantor_relationship = db.Column(db.String(100))
    guarantor_name = db.Column(db.String(180))
    guarantor_contact = db.Column(db.String(40))
    guarantor_address = db.Column(db.Text)
    billing_address = db.Column(db.Text)
    site_address = db.Column(db.Text)
    tax_number = db.Column(db.String(80))
    opening_balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "customer_code": self.customer_code,
            "customer_name": self.customer_name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "company": self.company,
            "main_mobile": self.main_mobile,
            "mobile_2": self.mobile_2,
            "mobile_3": self.mobile_3,
            "office_address": self.office_address,
            "office_email": self.office_email,
            "residential_address": self.residential_address,
            "gst_number": self.gst_number,
            "guarantor_relationship": self.guarantor_relationship,
            "guarantor_name": self.guarantor_name,
            "guarantor_contact": self.guarantor_contact,
            "guarantor_address": self.guarantor_address,
            "billing_address": self.billing_address,
            "site_address": self.site_address,
            "tax_number": self.tax_number,
            "opening_balance": float(self.opening_balance or 0),
            "is_active": bool(self.is_active),
        }


class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.BigInteger, primary_key=True)
    item_code = db.Column(db.String(50), unique=True, nullable=False)
    item_name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(100))
    unit = db.Column(db.String(30), nullable=False, default="Nos")
    total_stock = db.Column(db.Integer, nullable=False, default=0)
    initial_daily_rate = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    post_30_day_daily_rate = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    has_monthly_minimum = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "category": self.category,
            "unit": self.unit,
            "total_stock": self.total_stock,
            "initial_daily_rate": float(self.initial_daily_rate or 0),
            "post_30_day_daily_rate": float(self.post_30_day_daily_rate or 0),
            "has_monthly_minimum": bool(self.has_monthly_minimum),
            "is_active": bool(self.is_active),
        }
