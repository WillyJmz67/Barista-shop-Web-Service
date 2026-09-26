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

# Vercel busca `app` a nivel de módulo
__all__ = ["app"]
