import os
import json
from app import app, db
from models import Product

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///tienda.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

with app.app_context():
    db.create_all()

    existing = Product.query.count()
    if existing > 0:
        print(f"Base de datos ya tiene {existing} productos. Seed omitido.")
    else:
        with open("data/productos.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            p = Product(
                id=item["id"],
                nombre=item["nombre"],
                slug=item["slug"],
                descripcion=item.get("descripcion", ""),
                descripcion_corta=item.get("descripcion_corta", ""),
                precio=item["precio"],
                imagen=item.get("imagen", ""),
                categoria=item.get("categoria", "utensilios"),
                destacado=item.get("destacado", False),
                stock=item.get("stock", True),
            )
            db.session.add(p)

        db.session.commit()
        print(f"Se cargaron {len(data)} productos desde data/productos.json")
