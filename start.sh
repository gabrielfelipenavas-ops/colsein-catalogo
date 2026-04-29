#!/usr/bin/env bash
# start.sh - Arranque del servicio Colsein en Railway.
# Idempotente: NO sobreescribe datos del admin entre redeploys.
set -euo pipefail

# DATA_DIR es el volumen persistente montado por Railway. Default a /data
# si no se pasó (debe coincidir con el mount path configurado en Railway).
export DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

echo "[start] DATA_DIR=$DATA_DIR"
# Diagnóstico de env vars (solo longitud, NO valores)
echo "[start] ADMIN_USER length: ${#ADMIN_USER}  (esperado: 6 si vale 'felipe')"
echo "[start] ADMIN_PASS length: ${#ADMIN_PASS}  (esperado: 32 si tiene la pass generada)"
echo "[start] FLASK_SECRET_KEY length: ${#FLASK_SECRET_KEY}  (esperado: 64)"

# 1. Sembrar taxonomía la primera vez (luego admin la edita en el volumen)
if [ ! -f "$DATA_DIR/taxonomy_editable.json" ]; then
    echo "[start] sembrando taxonomy_editable.json en el volumen"
    cp taxonomy_editable.json "$DATA_DIR/taxonomy_editable.json"
fi

# 2. Crear/migrar la BD
python colsein_agent_v3.py init

# 3. Importar el seed SOLO si la BD aún no tiene productos
#    (así no pisamos productos agregados/scrapeados por admin tras un redeploy)
PRODUCT_COUNT=$(python -c "
import sqlite3, os
db = os.path.join(os.environ['DATA_DIR'], 'colsein.db')
con = sqlite3.connect(db)
n = con.execute('SELECT COUNT(*) FROM products').fetchone()[0]
print(n)
")
echo "[start] productos en BD: $PRODUCT_COUNT"
if [ "$PRODUCT_COUNT" = "0" ]; then
    echo "[start] BD vacía, importando seed 06_products_classified_v2.json"
    python colsein_agent_v3.py import-json 06_products_classified_v2.json
fi

# 4. Regenerar el HTML con la taxonomía actual del volumen
python colsein_agent_v3.py export-html "$DATA_DIR/colsein_app_v3.html"

# 5. Arrancar gunicorn (PORT lo inyecta Railway)
PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
echo "[start] gunicorn en 0.0.0.0:$PORT con $WORKERS workers"
exec gunicorn wsgi:app \
    --bind "0.0.0.0:$PORT" \
    --workers "$WORKERS" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
