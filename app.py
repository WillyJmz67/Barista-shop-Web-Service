import os
import json
import logging
import mercadopago
from urllib.parse import quote
from datetime import datetime
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, redirect, session, url_for, Response
)
from flask_wtf.csrf import CSRFProtect
from models import db, Product, Order, OrderItem

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# En Vercel serverless /var/task es read-only. Flask-SQLAlchemy intenta crear
# app.instance_path (por defecto /var/task/instance) en init_app().
# Redirigimos a /tmp (writable) para evitar OSError: [Errno 30] Read-only file system.
if os.environ.get("VERCEL"):
    app.instance_path = "/tmp"
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

# Secret key: Vercel + Supabase -> SIEMPRE por variable de entorno en producción.
# En serverless el filesystem es read-only, no se puede persistir .flask_secret.
_default_secret = os.environ.get("FLASK_SECRET_KEY")
_on_vercel = bool(os.environ.get("VERCEL"))
if _default_secret:
    app.secret_key = _default_secret
elif _on_vercel:
    # No romper el cold-start: usar clave efímera y loguear aviso.
    # Las sesiones admin no persistirán entre deploys si no se define la variable.
    logger.warning("FLASK_SECRET_KEY no definido en Vercel: usando clave efímera. Define la variable en el dashboard.")
    app.secret_key = os.urandom(32).hex()
elif os.environ.get("ENV", "").lower() == "production" or os.environ.get("FLASK_ENV", "").lower() == "production":
    raise RuntimeError("FLASK_SECRET_KEY debe estar definido en variables de entorno en producción")
else:
    # Desarrollo local: clave persistente en archivo local
    secret_file = Path(__file__).parent / ".flask_secret"
    try:
        if secret_file.exists():
            app.secret_key = secret_file.read_text().strip()
        else:
            app.secret_key = os.urandom(32).hex()
            secret_file.write_text(app.secret_key)
            try:
                secret_file.chmod(0o600)
            except OSError:
                pass
    except OSError:
        app.secret_key = os.urandom(32).hex()

# CSRF Protection
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = None  # Sin límite de tiempo para el token
csrf = CSRFProtect(app)

def _normalize_database_url(url: str) -> str:
    """Normaliza DATABASE_URL para Supabase / Postgres / SQLite."""
    if not url:
        return "sqlite:///tienda.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Supabase pooler (pgbouncer) recomienda statement_cache_size=0 con SQLAlchemy/psycopg2.
    # No lo forzamos aquí para no romper URLs locales, pero se documenta en .env.example.
    return url


DATABASE_URL = _normalize_database_url(os.environ.get("DATABASE_URL", "sqlite:///tienda.db"))
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if _IS_SQLITE:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
else:
    # Supabase Postgres (serverless): conexiones cortas, ping antes de usar,
    # reciclaje para evitar conexiones muertas del pooler.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {"connect_timeout": 10},
    }

MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "573173169936")

db.init_app(app)

# En Vercel (serverless) no hacer create_all() agresivo en cada cold-start.
# Las tablas se crean con supabase/schema.sql o seed_supabase.py.
# Solo auto-crear en SQLite local o si se permite explícitamente.
_AUTO_CREATE = os.environ.get("ALLOW_DB_CREATE", "1") == "1"
if _IS_SQLITE or (_AUTO_CREATE and not _on_vercel):
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            logger.warning(f"No se pudo auto-crear tablas: {e}")
elif _on_vercel:
    # Intento ligero y tolerante a fallos: si Supabase aún no tiene tablas,
    # las APIs devolverán [] en vez de romper el import.
    pass


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
    # Validar stock antes de crear el pedido
    for item in items:
        product = db.session.get(Product, item.get("id", 0))
        if product and product.stock is False:
            raise ValueError(f"Producto sin stock: {product.nombre}")
        if product and product.stock is True and item.get("cantidad", 1) > 999:
            # Límite razonable por producto
            raise ValueError(f"Cantidad inválida para {product.nombre}")
    
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


# Rutas absolutas basadas en app.root_path: en Vercel serverless el CWD
# no es necesariamente la raíz del proyecto (filesystem read-only).
_STATIC_DIRS = {
    "js": os.path.join(app.root_path, "js"),
    "css": os.path.join(app.root_path, "css"),
    "img": os.path.join(app.root_path, "img"),
    "data": os.path.join(app.root_path, "data"),
}


@app.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory(_STATIC_DIRS["js"], filename)


@app.route("/css/<path:filename>")
def css_files(filename):
    return send_from_directory(_STATIC_DIRS["css"], filename)


@app.route("/img/<path:filename>")
def img_files(filename):
    return send_from_directory(_STATIC_DIRS["img"], filename)


@app.route("/data/<path:filename>")
def data_files(filename):
    return send_from_directory(_STATIC_DIRS["data"], filename)


@app.route("/api/health")
def api_health():
    """Healthcheck para Vercel / Supabase."""
    status = {"ok": True, "db": "unknown"}
    try:
        db.session.execute(db.text("SELECT 1"))
        status["db"] = "up"
    except Exception as e:
        status["db"] = f"down: {e}"
    return jsonify(status)


@app.route("/api/productos")
def api_productos():
    try:
        productos = Product.query.filter_by(stock=True).order_by(Product.id).all()
    except Exception as e:
        logger.warning(f"/api/productos sin tablas o DB caída: {e}")
        return jsonify([])
    return jsonify([p.to_dict() for p in productos])


@app.route("/api/productos/destacados")
def api_productos_destacados():
    try:
        productos = Product.query.filter_by(destacado=True, stock=True).all()
    except Exception as e:
        logger.warning(f"/api/productos/destacados sin tablas o DB caída: {e}")
        return jsonify([])
    return jsonify([p.to_dict() for p in productos])


@app.route("/api/whatsapp-order", methods=["POST"])
def whatsapp_order():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Carrito vacío"}), 400

    shipping = data.get("shipping", {})
    try:
        order, total = create_order_from_cart(items, shipping)
    except ValueError as e:
        logger.warning(f"WhatsApp order validation failed: {e}")
        return jsonify({"error": str(e)}), 400

    url = build_whatsapp_url(items, total, shipping, order.id)
    logger.info(f"WhatsApp order created: order_id={order.id}, total={total}, items={len(items)}")
    return jsonify({"url": url, "order_id": order.id})


@app.route("/api/create_preference", methods=["POST"])
def create_preference():
    data = request.get_json() or {}
    items = data.get("items", [])
    shipping = data.get("shipping", {})

    if not items:
        return jsonify({"error": "Carrito vacío"}), 400

    try:
        order, total = create_order_from_cart(items, shipping)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

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
        logger.info(f"MercadoPago preference created for order {order.id}: {preference_id}")

        return jsonify({"init_point": init_point, "order_id": order.id})

    except Exception as e:
        logger.error(f"Error creating MercadoPago preference for order {order.id}: {e}")
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
                    order = db.session.get(Order, int(external_ref))
                    if order:
                        order.status = "Pagado"
                        order.payment_id = str(payment_id)
                        db.session.commit()
                        logger.info(f"Order {order.id} marked as Pagado via webhook (payment {payment_id})")
            except Exception as e:
                logger.error(f"Error processing MercadoPago webhook: {e}")
    return jsonify({"ok": True})


# ─── ADMIN ──────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            logger.info("Admin login successful")
            return redirect(url_for("admin_dashboard"))
        logger.warning("Admin login failed: invalid password")
        return render_template("admin/login.html", error="Contraseña incorrecta")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    logger.info("Admin logout")
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
        logger.info(f"Admin created product: {p.id} - {p.nombre}")
        return redirect(url_for("admin_productos"))
    return render_template("admin/product_form.html", producto=None)


@app.route("/admin/productos/editar/<int:id>", methods=["GET", "POST"])
@require_admin
def admin_producto_editar(id):
    p = db.get_or_404(Product, id)
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
        logger.info(f"Admin updated product: {p.id} - {p.nombre}")
        return redirect(url_for("admin_productos"))
    return render_template("admin/product_form.html", producto=p)


@app.route("/admin/productos/eliminar/<int:id>", methods=["POST"])
@require_admin
def admin_producto_eliminar(id):
    p = db.get_or_404(Product, id)
    nombre = p.nombre
    db.session.delete(p)
    db.session.commit()
    logger.info(f"Admin deleted product: {id} - {nombre}")
    return redirect(url_for("admin_productos"))


@app.route("/admin/pedidos")
@require_admin
def admin_pedidos():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin/orders.html", orders=orders)


@app.route("/admin/pedidos/<int:id>/estado", methods=["POST"])
@require_admin
def admin_pedido_estado(id):
    order = db.get_or_404(Order, id)
    order.status = request.form.get("status", order.status)
    db.session.commit()
    logger.info(f"Admin updated order {id} status to {order.status}")
    return redirect(url_for("admin_pedidos"))


# ─── PÁGINAS PÚBLICAS EXTRA ────────────────────────

@app.route("/pg/exito")
def pg_exito():
    order_id = request.args.get("order_id")
    if order_id:
        try:
            order = db.session.get(Order, int(order_id))
        except (ValueError, TypeError):
            order = None
        if order:
            order.status = "Pagado"
            db.session.commit()
            logger.info(f"Order {order_id} marked as Pagado via success page")
    return render_template("exito.html", order_id=order_id)


@app.route("/pg/error")
def pg_error():
    logger.warning("MercadoPago payment error page accessed")
    return render_template("error.html")


@app.route("/pg/pending")
def pg_pending():
    logger.info("MercadoPago payment pending page accessed")
    return render_template("pending.html")


# ─── ERROR HANDLERS ───────────────────────────────────

@app.teardown_appcontext
def shutdown_session(exception=None):
    # Higiene del pool en serverless: devuelve la conexión al pooler de Supabase.
    db.session.remove()


@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 Not Found: {request.path}")
    try:
        return render_template("error.html", message="Página no encontrada"), 404
    except Exception:
        return Response("Página no encontrada", status=404, mimetype="text/plain")


@app.errorhandler(500)
def internal_error(e):
    # logger.exception incluye el traceback completo: visible en Vercel > Logs.
    logger.exception(f"500 Internal Server Error: {e}")
    try:
        return render_template("error.html", message="Error interno del servidor"), 500
    except Exception:
        # Si hasta el template de error falla (ej. bundle sin templates),
        # devolver texto plano en vez de romper la función serverless.
        return Response("Error interno del servidor", status=500, mimetype="text/plain")


# CSRF exemptions for public APIs (must be after route definitions)
csrf.exempt(whatsapp_order)
csrf.exempt(create_preference)
csrf.exempt(mercadopago_webhook)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
