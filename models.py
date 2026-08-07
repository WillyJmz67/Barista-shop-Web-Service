import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, default="")
    descripcion_corta = db.Column(db.String(300), default="")
    precio = db.Column(db.Integer, nullable=False)
    imagen = db.Column(db.String(500), default="")
    categoria = db.Column(db.String(50), default="utensilios")
    destacado = db.Column(db.Boolean, default=False)
    stock = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "slug": self.slug,
            "descripcion": self.descripcion,
            "descripcion_corta": self.descripcion_corta,
            "precio": self.precio,
            "imagen": self.imagen,
            "categoria": self.categoria,
            "destacado": self.destacado,
            "stock": self.stock,
        }


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), default="")
    customer_email = db.Column(db.String(200), default="")
    customer_phone = db.Column(db.String(50), default="")
    shipping_name = db.Column(db.String(200), default="")
    shipping_address = db.Column(db.Text, default="")
    shipping_city = db.Column(db.String(100), default="")
    shipping_phone = db.Column(db.String(50), default="")
    shipping_notes = db.Column(db.Text, default="")
    total = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default="Pendiente")
    payment_id = db.Column(db.String(200), default="")
    preference_id = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "customer_phone": self.customer_phone,
            "shipping_name": self.shipping_name,
            "shipping_address": self.shipping_address,
            "shipping_city": self.shipping_city,
            "shipping_phone": self.shipping_phone,
            "shipping_notes": self.shipping_notes,
            "total": self.total,
            "status": self.status,
            "payment_id": self.payment_id,
            "preference_id": self.preference_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "items": [i.to_dict() for i in self.items],
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    product_id = db.Column(db.Integer)
    product_name = db.Column(db.String(200))
    cantidad = db.Column(db.Integer, default=1)
    precio = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "cantidad": self.cantidad,
            "precio": self.precio,
        }
