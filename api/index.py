"""Entry-point para Vercel Serverless (Python).

Vercel importa este módulo y sirve la variable `app` (Flask WSGI).
"""
import os
import sys
from pathlib import Path

# Asegura que la raíz del proyecto esté en sys.path para `import app`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("VERCEL", "1")

from app import app  # noqa: E402


class VercelPathFix:
    """Red de seguridad: si el runtime entrega PATH_INFO del destino
    (/api/index) en vez de la ruta original, intenta recuperarla de
    REQUEST_URI/RAW_URI antes de que Flask resuelva rutas."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in ("/api/index", "/api/index.py"):
            for key in ("REQUEST_URI", "RAW_URI", "HTTP_X_ORIGINAL_URL"):
                raw = environ.get(key, "")
                if raw and not raw.startswith("/api/index"):
                    environ["PATH_INFO"] = raw.split("?", 1)[0]
                    break
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathFix(app.wsgi_app)

# Vercel busca `app` a nivel de módulo
__all__ = ["app"]
