"""Seed de productos. Funciona con SQLite local y con Supabase Postgres.

Uso local:
    python seed.py

Uso Supabase (PowerShell):
    $env:DATABASE_URL="postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres?sslmode=require"
    python seed.py

En Supabase usa preferiblemente la URL del Connection Pooling (puerto 6543)
para no agotar conexiones. Primero ejecuta supabase/schema.sql en el SQL Editor.
"""
import os
import json
from pathlib import Path

from app import app, db
from models import Product

BASE = Path(__file__).resolve().parent


def _normalize(url: str) -> str:
    if not url:
        return "sqlite:///tienda.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _normalize(os.environ.get("DATABASE_URL", "sqlite:///tienda.db"))
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

with app.app_context():
    db.create_all()

    existing = Product.query.count()
    if existing > 0:
        print(f"Base de datos ya tiene {existing} productos. Seed omitido.")
    else:
        with open(BASE / "data" / "productos.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            # No forzar id en Postgres con identity: deja que la secuencia lo asigne,
            # pero conserva compatibilidad con SQLite existente.
            kwargs = dict(
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
            if DATABASE_URL.startswith("sqlite"):
                kwargs["id"] = item["id"]
            p = Product(**kwargs)
            db.session.add(p)

        db.session.commit()
        print(f"Se cargaron {len(data)} productos desde data/productos.json")
