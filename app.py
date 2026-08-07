import os
import json
import mercadopago
from urllib.parse import quote
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, redirect, session, url_for, Response
)
from models import db, Product, Order, OrderItem

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///tienda.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "573173169936")

db.init_app(app)

with app.app_context():
    db.create_all()


def require_admin(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


def _format_cop(amount):
    return f"${int(amount):,}"


def build_whatsapp_url(items, total, shipping=None, order_id=None):
    shipping = shipping or {}
    lines = ["Hola! 👋 Quiero hacer este pedido:"]
    for item in items:
        lines.append(
            f"{item['nombre']} × {item['cantidad']} = {_format_cop(item['precio'])} c/u"
        )
    lines.append(f"\nTotal: {_format_cop(total)} COP")
    if shipping.get("name"):
        lines.append(f"\nEnvío a: {shipping['name']}")
        if shipping.get("address"):
            lines.append(shipping["address"])
        if shipping.get("city"):
            lines.append(shipping["city"])
        if shipping.get("phone"):
            lines.append(f"Tel: {shipping['phone']}")
    if order_id:
        lines.append(f"\nPedido #{order_id}")
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(chr(10).join(lines))}"


def create_order_from_cart(items, shipping=None):
    shipping = shipping or {}
    total = sum(int(item["cantidad"]) * float(item["precio"]) for item in items)
    order = Order(
        total=int(total),
        status="Pendiente",
        customer_name=shipping.get("name", ""),
        customer_email=shipping.get("email", ""),
        customer_phone=shipping.get("phone", ""),
        shipping_name=shipping.get("name", ""),
        shipping_address=shipping.get("address", ""),
        shipping_city=shipping.get("city", ""),
        shipping_phone=shipping.get("phone", ""),
    )
    for item in items:
        order.items.append(OrderItem(
            product_id=item.get("id", 0),
            product_name=item["nombre"],
            cantidad=int(item["cantidad"]),
            precio=int(item["precio"]),
        ))
    db.session.add(order)
    db.session.commit()
    return order, int(total)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/productos/")
def productos():
    return render_template("productos.html")


@app.route("/nosotros/")
def nosotros():
    return render_template("nosotros.html")


@app.route("/js/config.js")
def config_js():
    config = {
        "WHATSAPP_NUMBER": WHATSAPP_NUMBER,
        "WHATSAPP_MESSAGE": quote("Hola, quiero información sobre sus productos"),
        "SHOP_NAME": os.environ.get("SHOP_NAME", "Café & Barista Shop"),
        "SHOP_LOCATION": os.environ.get("SHOP_LOCATION", "Villavicencio, Colombia"),
        "CURRENCY": "COP",
        "HAS_MERCADOPAGO": bool(MP_ACCESS_TOKEN),
    }
    body = f"const CONFIG = {json.dumps(config, ensure_ascii=False)};"
    return Response(body, mimetype="application/javascript")


@app.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory("js", filename)


@app.route("/css/<path:filename>")
def css_files(filename):
    return send_from_directory("css", filename)


@app.route("/img/<path:filename>")
def img_files(filename):
    return send_from_directory("img", filename)


@app.route("/data/<path:filename>")
def data_files(filename):
    return send_from_directory("data", filename)


@app.route("/api/productos")
def api_productos():
    productos = Product.query.filter_by(stock=True).order_by(Product.id).all()
    return jsonify([p.to_dict() for p in productos])


@app.route("/api/productos/destacados")
def api_productos_destacados():
    productos = Product.query.filter_by(destacado=True, stock=True).all()
    return jsonify([p.to_dict() for p in productos])


@app.route("/api/whatsapp-order", methods=["POST"])
def whatsapp_order():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Carrito vacío"}), 400

    shipping = data.get("shipping", {})
    order, total = create_order_from_cart(items, shipping)
    url = build_whatsapp_url(items, total, shipping, order.id)
    return jsonify({"url": url, "order_id": order.id})


@app.route("/api/create_preference", methods=["POST"])
def create_preference():
    data = request.get_json() or {}
    items = data.get("items", [])
    shipping = data.get("shipping", {})

    if not items:
        return jsonify({"error": "Carrito vacío"}), 400

    order, total = create_order_from_cart(items, shipping)

    if not MP_ACCESS_TOKEN:
        return jsonify({
            "fallback": True,
            "url": build_whatsapp_url(items, total, shipping, order.id),
            "order_id": order.id,
        })

    try:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        preference_items = []
        for item in items:
            preference_items.append({
                "title": item["nombre"],
                "quantity": int(item["cantidad"]),
                "unit_price": float(item["precio"]),
                "currency_id": "COP",
            })

        payer = {}
        if shipping.get("email"):
            payer["email"] = shipping["email"]
        if shipping.get("name"):
            payer["name"] = shipping["name"].split()[0] if shipping["name"].split() else shipping["name"]
        if shipping.get("phone"):
            payer["phone"] = {"number": shipping["phone"]}

        preference_data = {
            "items": preference_items,
            "payer": payer if payer else None,
            "back_urls": {
                "success": request.host_url + f"pg/exito?order_id={order.id}",
                "failure": request.host_url + f"pg/error?order_id={order.id}",
                "pending": request.host_url + f"pg/pending?order_id={order.id}",
            },
            "auto_return": "approved",
            "statement_descriptor": "CAFE & BARISTA",
            "external_reference": str(order.id),
        }
        preference_data = {k: v for k, v in preference_data.items() if v is not None}

        result = sdk.preference().create(preference_data)
        init_point = result.get("init_point") or result.get("response", {}).get("init_point")
        preference_id = result.get("id") or result.get("response", {}).get("id")

        order.preference_id = preference_id or ""
        db.session.commit()

        return jsonify({"init_point": init_point, "order_id": order.id})

    except Exception:
        return jsonify({
            "fallback": True,
            "url": build_whatsapp_url(items, total, shipping, order.id),
            "order_id": order.id,
        })


@app.route("/api/mercadopago/webhook", methods=["POST"])
def mercadopago_webhook():
    data = request.get_json()
    if data and data.get("type") == "payment":
        payment_id = data.get("data", {}).get("id")
        if payment_id and MP_ACCESS_TOKEN:
            try:
                sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
                payment = sdk.payment().get(payment_id)
                status = payment.get("response", {}).get("status")
                external_ref = payment.get("response", {}).get("external_reference")
                if external_ref and status == "approved":
                    order = Order.query.get(int(external_ref))
                    if order:
                        order.status = "Pagado"
                        order.payment_id = str(payment_id)
                        db.session.commit()
            except Exception:
                pass
    return jsonify({"ok": True})


# ─── ADMIN ──────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/login.html", error="Contraseña incorrecta")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/")
@require_admin
def admin_dashboard():
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    pending_orders = Order.query.filter_by(status="Pendiente").count()
    paid_orders = Order.query.filter_by(status="Pagado").count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    total_products = Product.query.count()
    return render_template("admin/dashboard.html",
                           total_orders=total_orders,
                           total_revenue=total_revenue,
                           pending_orders=pending_orders,
                           paid_orders=paid_orders,
                           recent_orders=recent_orders,
                           total_products=total_products)


@app.route("/admin/productos")
@require_admin
def admin_productos():
    productos = Product.query.order_by(Product.id).all()
    return render_template("admin/products.html", productos=productos)


@app.route("/admin/productos/nuevo", methods=["GET", "POST"])
@require_admin
def admin_producto_nuevo():
    if request.method == "POST":
        p = Product(
            nombre=request.form["nombre"],
            slug=request.form["slug"],
            descripcion=request.form.get("descripcion", ""),
            descripcion_corta=request.form.get("descripcion_corta", ""),
            precio=int(request.form["precio"]),
            imagen=request.form.get("imagen", ""),
            categoria=request.form.get("categoria", "utensilios"),
            destacado=request.form.get("destacado") == "on",
            stock=request.form.get("stock") == "on",
        )
        db.session.add(p)
        db.session.commit()
        return redirect(url_for("admin_productos"))
    return render_template("admin/product_form.html", producto=None)


@app.route("/admin/productos/editar/<int:id>", methods=["GET", "POST"])
@require_admin
def admin_producto_editar(id):
    p = Product.query.get_or_404(id)
    if request.method == "POST":
        p.nombre = request.form["nombre"]
        p.slug = request.form["slug"]
        p.descripcion = request.form.get("descripcion", "")
        p.descripcion_corta = request.form.get("descripcion_corta", "")
        p.precio = int(request.form["precio"])
        p.imagen = request.form.get("imagen", "")
        p.categoria = request.form.get("categoria", "utensilios")
        p.destacado = request.form.get("destacado") == "on"
        p.stock = request.form.get("stock") == "on"
        db.session.commit()
        return redirect(url_for("admin_productos"))
    return render_template("admin/product_form.html", producto=p)


@app.route("/admin/productos/eliminar/<int:id>", methods=["POST"])
@require_admin
def admin_producto_eliminar(id):
    p = Product.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for("admin_productos"))


@app.route("/admin/pedidos")
@require_admin
def admin_pedidos():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin/orders.html", orders=orders)


@app.route("/admin/pedidos/<int:id>/estado", methods=["POST"])
@require_admin
def admin_pedido_estado(id):
    order = Order.query.get_or_404(id)
    order.status = request.form.get("status", order.status)
    db.session.commit()
    return redirect(url_for("admin_pedidos"))


# ─── PÁGINAS PÚBLICAS EXTRA ────────────────────────

@app.route("/pg/exito")
def pg_exito():
    order_id = request.args.get("order_id")
    if order_id:
        order = Order.query.get(order_id)
        if order:
            order.status = "Pagado"
            db.session.commit()
    return render_template("exito.html", order_id=order_id)


@app.route("/pg/error")
def pg_error():
    return render_template("error.html")


@app.route("/pg/pending")
def pg_pending():
    return render_template("pending.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
