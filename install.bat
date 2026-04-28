@echo off
REM install.bat - Setup automático del catálogo Colsein (Windows)
REM Uso: doble clic o "install.bat" desde cmd

echo ============================================================
echo   COLSEIN CATALOGO . Instalacion automatica (Windows)
echo ============================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo X Python no encontrado. Instalalo desde python.org
    echo   Asegurate de marcar "Add Python to PATH" durante la instalacion
    pause
    exit /b 1
)
echo OK: Python disponible

REM Verificar archivos
echo.
echo Verificando archivos en la carpeta actual...
set MISSING=0
for %%F in (colsein_agent_v3.py colsein_app_template.html taxonomy_editable.json 06_products_classified_v2.json) do (
    if exist %%F (
        echo   OK: %%F
    ) else (
        echo   X FALTA: %%F
        set MISSING=1
    )
)
if %MISSING%==1 (
    echo.
    echo X Faltan archivos. Descarga TODOS los archivos a esta carpeta.
    pause
    exit /b 1
)

REM Instalar dependencias
echo.
echo Instalando dependencias Python...
pip install --quiet flask requests beautifulsoup4 lxml
if errorlevel 1 (
    echo Aviso: instalacion de dependencias fallo. Ejecuta manualmente:
    echo   pip install flask requests beautifulsoup4 lxml
)

REM Setup
echo.
echo Inicializando base de datos...
python colsein_agent_v3.py init

echo.
echo Importando 443 productos iniciales...
python colsein_agent_v3.py import-json 06_products_classified_v2.json

echo.
echo Generando HTML del frontend...
python colsein_agent_v3.py export-html colsein_app_v3.html

echo.
echo ============================================================
echo   OK INSTALACION COMPLETADA
echo ============================================================
echo.
echo Para arrancar el sistema:
echo   python colsein_agent_v3.py serve --port 8000
echo.
echo Despues abre en tu navegador:
echo   http://localhost:8000
echo.
echo Para entrar en modo administrador:
echo   Click en "Invitado" arriba a la derecha
echo   Usuario: Felipe / Contrasena: Felipe
echo.
pause
