# Colsein Catálogo · Cómo arrancar

## Lo que necesitas descargar (8 archivos)

Pon todos en una sola carpeta, ej: `C:\colsein-catalogo` o `~/colsein-catalogo`

| Archivo | Para qué sirve |
|---|---|
| `colsein_agent_v3.py` | El programa Python (backend) |
| `colsein_app_template.html` | Plantilla del frontend (NO la abras directamente) |
| `taxonomy_editable.json` | Categorías y filtros (editable) |
| `06_products_classified_v2.json` | 443 productos iniciales |
| `install.sh` | Setup automático Mac/Linux |
| `install.bat` | Setup automático Windows |
| `README_workflow.md` | Documentación completa (referencia) |
| `INICIO_RAPIDO.md` | Este archivo |

## Instalación rápida (1 sola vez)

### Mac / Linux

```bash
cd ~/colsein-catalogo
chmod +x install.sh
./install.sh
```

### Windows

Doble clic a `install.bat` (o desde cmd: `install.bat`)

El script verifica Python, instala las dependencias, crea la BD, carga los
443 productos y genera el HTML. Tarda ~30 segundos.

## Arrancar el sistema (cada vez que quieras usarlo)

```bash
python3 colsein_agent_v3.py serve --port 8000
```

O en Windows:
```
python colsein_agent_v3.py serve --port 8000
```

Después abre en tu navegador:

**http://localhost:8000**

## Modo invitado vs administrador

- **Invitado** (default): navega catálogo, filtros, agrega producto local
- **Admin** (Felipe / Felipe): además puede buscar productos nuevos en línea
  y actualizar filtros automáticamente

Para entrar como admin:
1. Click en el badge **"Invitado"** arriba a la derecha
2. Usuario: **Felipe** · Contraseña: **Felipe**
3. El badge cambia a azul y aparecen 2 botones nuevos en la barra

## Si algo no funciona

| Problema | Solución |
|---|---|
| Doble clic al HTML no muestra nada | NO uses doble clic. Arranca el servidor con `serve` y abre `http://localhost:8000` |
| "Frontend no encontrado" en navegador | Falta generar el HTML: `python3 colsein_agent_v3.py export-html colsein_app_v3.html` |
| Badge "Invitado" no responde | Servidor no está corriendo. Arráncalo con `serve` |
| El login dice "credenciales inválidas" | Felipe con F mayúscula, ambos campos |
| Las búsquedas web devuelven 403 | Los fabricantes bloquean bots. Usa Claude AI con catálogos PDF en su lugar |

## Para uso con Claude Code

Una vez instalado, abre Claude Code en la carpeta del proyecto y dile:

> "Ya tengo el sistema Colsein instalado en este directorio. Por favor lee
> el `README_workflow.md` para entender el sistema, después arranca el
> servidor en background y ayúdame a [tu tarea]."

Tareas típicas que Claude Code puede hacer:

- "Genera 30 productos nuevos de la familia SICK W12 en formato JSON e impórtalos"
- "Lee `taxonomy_editable.json` y agrega un atributo nuevo `cable_outer_jacket`
  con valores PVC, silicona, poliuretano, después conéctalo como filtro de la
  hoja `cables-conexion.cables.especiales`"
- "Corre `suggest-filters --output sug.md`, lee el archivo, y aplica las 3
  sugerencias con score más alto"

## Para más detalles

Lee `README_workflow.md` que tiene todos los comandos del CLI, los endpoints
HTTP del servidor, y ejemplos completos.
