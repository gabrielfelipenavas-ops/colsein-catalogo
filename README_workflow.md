# Colsein Catálogo v4 · Guía completa

Sistema con SQLite local, frontend offline, imágenes de productos, modo
administrador con login, búsqueda de productos nuevos en línea, y actualización
automática de filtros.

## Lo nuevo en v4

- **Modo administrador** con login Felipe/Felipe (y aviso honesto sobre limitaciones de seguridad)
- **Detección automática** del servidor Flask (banner verde si está corriendo, gris si offline)
- **Botón "Buscar productos"** (admin): el servidor visita las webs de los fabricantes y agrega los productos nuevos a SQLite
- **Botón "Actualizar filtros"** (admin): el servidor analiza la BD, aplica automáticamente los filtros con `attribute_id` ya definido, y genera un prompt para Claude Code para los que faltan
- **Endpoint /api/health**: el frontend detecta solo si el servidor está disponible

## Arquitectura

```
                ┌──────────────────────────────┐
                │  taxonomy_editable.json      │ ← editable a mano + automático
                └──────────┬───────────────────┘
                           │ lee/escribe
                           ▼
┌──────────────┐   POST   ┌─────────────────┐  serve  ┌──────────────────┐
│ Frontend     │◄────────►│ colsein_agent.py│◄───────►│ http://localhost │
│ Admin panel  │  /api/   │ + SQLite        │         │      :8000        │
│ Login Felipe │  admin/* │                 │         └──────────────────┘
└──────────────┘          └─────────┬───────┘
                                    │ scrape
                                    ▼
                          ┌──────────────────────┐
                          │  Webs de fabricantes │
                          └──────────────────────┘
```

## Setup inicial

```bash
cd ~/colsein-catalogo/

# 1. Dependencias
pip install requests beautifulsoup4 lxml flask

# 2. Crear/migrar BD
python3 colsein_agent_v3.py init

# 3. Cargar 443 productos iniciales
python3 colsein_agent_v3.py import-json 06_products_classified_v2.json

# 4. Generar HTML
python3 colsein_agent_v3.py export-html colsein_app_v3.html

# 5. Levantar servidor (necesario para modo admin e imágenes locales)
python3 colsein_agent_v3.py serve --port 8000
```

Luego abre **http://localhost:8000** en el navegador (NO doble clic al HTML
si quieres usar el modo admin).

## Modo invitado vs admin

**Modo invitado** (default, todos los usuarios):
- Navega el catálogo, filtros progresivos, detalle con imagen
- Importar/exportar JSON manualmente
- Agregar producto desde formulario (queda en memoria del navegador hasta
  que exportes el JSON e importes con Python)

**Modo admin** (login Felipe/Felipe):
- Todo lo anterior +
- **Buscar productos**: scraping en línea (≥200 nuevos por marca o general)
- **Actualizar filtros**: análisis automático + auto-aplicación + Claude Code prompt
- Operaciones modifican SQLite directamente

### Cómo entrar como admin

1. Asegúrate de tener el servidor corriendo: `python3 colsein_agent_v3.py serve --port 8000`
2. Abre `http://localhost:8000`
3. Click en el badge "Invitado" arriba a la derecha
4. Usuario: **Felipe** · Contraseña: **Felipe**
5. El badge cambia a azul "Felipe (admin)" y aparecen 2 botones nuevos en la barra

### Aviso honesto sobre seguridad

El login Felipe/Felipe **no es seguridad real**. Sirve para separar interfaces
(admin vs invitado) pero alguien con acceso a tu computadora o a la red local
podría acceder al servidor sin login leyendo el código fuente. Para uso público
con varios usuarios necesitas:
- Cambiar las credenciales por algo único
- HTTPS (no HTTP)
- Tokens de larga duración con expiración real
- Servir desde un dominio en lugar de localhost

Para uso interno en tu computadora, este nivel está bien.

## Buscar productos nuevos (admin)

Click en **"Buscar productos"** → modal:

- **Marca**: una específica (SICK, ABB, etc.) o "Todas las marcas (general)"
- **Cantidad mínima**: 200 (default), puedes subir/bajar

El servidor:
1. Visita la URL del fabricante con rate-limit de 1s
2. Lee el HTML, extrae enlaces a productos
3. Compara contra los URLs ya en BD (no duplica)
4. Inserta los nuevos en SQLite con leaf=`needs_classification`

**Limitación real:** muchos fabricantes industriales (SICK, Phoenix Contact)
bloquean bots con HTTP 403. Cuando esto pase, la app te lo dice claramente
en el log. Para esos casos:

1. Pídele a Claude AI que te genere productos a partir de un PDF de catálogo
2. Importa con: `python3 colsein_agent_v3.py import-json productos_de_claude.json`

Después de buscar productos, los nuevos quedan sin clasificar. Para
clasificarlos:

```bash
python3 colsein_agent_v3.py export-json sin_clasificar.json
# → pásale el JSON a Claude AI: "clasifica estos productos según mi taxonomía"
# → Claude te devuelve clasificado.json
python3 colsein_agent_v3.py import-json clasificado.json --replace
python3 colsein_agent_v3.py export-html colsein_app_v3.html
```

## Actualizar filtros (admin)

Click en **"Actualizar filtros"** → modal:

- **Mínimo productos por hoja**: solo analiza hojas con N+ productos
- **Score mínimo**: solo aplica auto los filtros con score ≥ X (0-1)
- **Auto-aplicar**: marcar para aplicar automáticamente los que ya tienen `attribute_id`

El servidor:
1. Calcula entropía Shannon × cobertura de cada atributo por hoja
2. Lista los mejores filtros que NO están aún declarados
3. Si auto-apply está marcado:
   - Los que tienen `attribute_id` ya definido → los conecta a la hoja
   - Los que necesitan definición nueva → genera prompt para Claude Code
4. Si aplicó algo: regenera `colsein_app_v3.html` automáticamente
5. Tú recargas la página y los filtros nuevos aparecen

### Cuándo necesitas Claude Code

Si el atributo discriminador es un campo **nuevo** que no está en
`attribute_definitions`, la app no puede inventarse un label legible
sola. Por eso te genera un prompt como:

```markdown
# Tarea: definir atributos faltantes en taxonomy_editable.json

Hoja: cables-conexion.cables.especiales
- field: cable_outer_jacket (kind sugerido: enum, score 0.4)
- valores típicos: silicone, PVC FR
- Crea attribute_id en snake_case con label legible. Ejemplo:
  ```json
  "<NUEVO_ID>": {"label": "<Etiqueta humana>", "kind": "enum", "field": "cable_outer_jacket"}
  ```
```

Lo copias, abres Claude Code en la carpeta del proyecto y se lo pegas.
Claude Code edita `taxonomy_editable.json`, valida la sintaxis, regenera
el HTML, y listo.

## Imágenes (igual que v3)

```bash
# Asignar URL externa
python3 colsein_agent_v3.py set-image sick-wl18-3p430 \
    --url "https://www.sick.com/img/wl18.jpg"

# Cargar archivo local (se guarda como blob en SQLite)
python3 colsein_agent_v3.py set-image sick-wl18-3p430 \
    --file ./fotos/wl18.jpg

# Descarga masiva URL→blob (respaldo local)
python3 colsein_agent_v3.py download-images --brand sick --limit 50
```

**Para que las imágenes locales (blobs) se vean en el navegador**, debes
usar el servidor Flask. Si abres el HTML con doble clic, solo funcionarán
las URLs externas.

## Comandos completos del CLI

| Comando | Qué hace |
|---|---|
| `init` | Crea/migra BD |
| `import-json <archivo>` | Importa productos JSON |
| `export-json <archivo>` | Exporta BD a JSON |
| `export-html <archivo>` | Genera HTML autosuficiente |
| `add-product` | Agrega 1 producto interactivo |
| `add-leaf <id> <label>` | Agrega categoría hoja |
| `add-filter <hoja> <attr>` | Conecta filtro a hoja |
| `set-image <id> --url …` | Asigna imagen por URL |
| `set-image <id> --file …` | Carga imagen local |
| `download-images [--brand X] [--limit N]` | Descarga URLs como blobs |
| `suggest-filters [--output prompt.md]` | Sugiere filtros (CLI) |
| `stats` | Estadísticas |
| `refine` | Limpia y valida |
| `scrape --brand X` | Scraping CLI |
| `serve [--port 8000]` | Servidor Flask + endpoints admin |

## Endpoints HTTP del servidor

```
GET  /                              HTML del catálogo
GET  /api/health                    Healthcheck
GET  /api/products                  Lista de productos JSON
GET  /api/products/<id>/image       Imagen local (blob)
GET  /api/taxonomy                  Taxonomía y filtros
POST /api/products                  Agregar producto

POST /api/admin/login               { user, password } → { ok, token }
POST /api/admin/logout              (con header X-Admin-Token)
GET  /api/admin/stats               (con header X-Admin-Token)
POST /api/admin/find-products       { brand?, target } → resultado scraping
POST /api/admin/refresh-filters     { auto_apply?, min_score?, min_products? }
POST /api/admin/regenerate-html     Regenera el HTML
```

## Flujo completo de crecimiento

```
1. (admin) Inicia sesión con Felipe/Felipe
2. (admin) Click "Buscar productos" → marca SICK, target 200
3. (admin) Si los fabricantes bloquean: pide a Claude AI generar JSON
4. (admin) Importa el JSON con productos clasificados
5. (admin) Cuando una hoja tiene 5+ productos → "Actualizar filtros"
6. (admin) Auto-aplica los que se pueden, copia el prompt para los demás
7. (admin) Pega el prompt en Claude Code → define los atributos faltantes
8. (admin) Recarga el navegador → nuevos filtros visibles
9. (todos) Navegan el catálogo con filtros progresivos estilo SICK
```

## Tabla de troubleshooting

| Síntoma | Causa | Fix |
|---|---|---|
| Badge "Invitado" no clickeable | Servidor offline | `python3 colsein_agent_v3.py serve` |
| "Servidor offline" en login | No abriste por http://localhost | Usa el servidor, no doble clic al HTML |
| Buscar productos da 0 resultados | Fabricante bloquea bots (403) | Usa Claude AI con PDF del catálogo |
| Actualizar filtros no aplicó nada | Score insuficiente o ya declarados | Baja `min_score` a 0.4 |
| Imágenes locales no aparecen | HTML abierto con doble clic | Abre vía http://localhost |
| Filtro nuevo no aparece tras aplicar | HTML no se regeneró | `export-html colsein_app_v3.html` y recarga (Ctrl+R) |

## Notas técnicas

- Los tokens admin viven en memoria del servidor: si reinicias `serve`, hay que volver a hacer login
- El `min_score` ideal está entre 0.5 y 0.7. Score 1.0 = filtro perfectamente discriminante
- Los filtros se aplican en orden: primero los más recientes en el array → aparecen al final del panel
- Si un atributo ya existe en otra hoja, el sistema lo reconoce y no necesita Claude Code
