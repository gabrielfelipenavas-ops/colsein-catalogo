#!/bin/bash
# install.sh - Setup automático del catálogo Colsein
# Uso: bash install.sh

set -e  # detener si hay error

echo "════════════════════════════════════════════════════════════"
echo "  COLSEIN CATÁLOGO · Instalación automática"
echo "════════════════════════════════════════════════════════════"
echo

# Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 no encontrado. Instálalo desde python.org primero."
    exit 1
fi
echo "✓ Python 3 disponible: $(python3 --version)"

# Verificar archivos requeridos
echo
echo "Verificando archivos en la carpeta actual..."
REQUIRED=("colsein_agent_v3.py" "colsein_app_template.html" "taxonomy_editable.json" "06_products_classified_v2.json")
MISSING=()
for f in "${REQUIRED[@]}"; do
    if [ -f "$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ FALTA: $f"
        MISSING+=("$f")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo
    echo "✗ Faltan archivos. Asegúrate de descargar TODOS los archivos a esta carpeta."
    exit 1
fi

# Instalar dependencias
echo
echo "Instalando dependencias Python..."
pip install --quiet --break-system-packages flask requests beautifulsoup4 lxml 2>/dev/null || \
pip install --quiet flask requests beautifulsoup4 lxml || \
pip3 install --quiet flask requests beautifulsoup4 lxml || {
    echo "⚠ No se pudieron instalar las dependencias automáticamente"
    echo "  Ejecuta manualmente: pip install flask requests beautifulsoup4 lxml"
}

# Setup BD
echo
echo "Inicializando base de datos..."
python3 colsein_agent_v3.py init

echo
echo "Importando 443 productos iniciales..."
python3 colsein_agent_v3.py import-json 06_products_classified_v2.json

echo
echo "Generando HTML del frontend..."
python3 colsein_agent_v3.py export-html colsein_app_v3.html

echo
echo "════════════════════════════════════════════════════════════"
echo "  ✓ INSTALACIÓN COMPLETADA"
echo "════════════════════════════════════════════════════════════"
echo
echo "Para arrancar el sistema:"
echo "  python3 colsein_agent_v3.py serve --port 8000"
echo
echo "Después abre en tu navegador:"
echo "  http://localhost:8000"
echo
echo "Para entrar en modo administrador:"
echo "  Click en 'Invitado' arriba a la derecha"
echo "  Usuario: Felipe / Contraseña: Felipe"
echo
