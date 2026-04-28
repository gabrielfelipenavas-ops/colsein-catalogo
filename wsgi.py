"""WSGI entrypoint para gunicorn.

Uso:
  gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120

La inicialización de la BD, importación del seed JSON y generación del HTML
se hacen en `start.sh` antes de arrancar gunicorn (no aquí, para evitar que
cada worker reinicialice).
"""
from colsein_agent_v3 import build_app

app = build_app()
