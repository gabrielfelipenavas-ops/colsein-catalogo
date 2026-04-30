# Pipeline de ingesta de catálogos PDF

Este documento describe cómo procesar un PDF de catálogo de un fabricante
(SICK, Phoenix Contact, etc.) y subirlo al catálogo público con productos,
filtros progresivos e imágenes.

## Requisitos previos

Local:
```bash
pip install pypdf pymupdf
```

El servidor en Railway ya tiene los endpoints necesarios:
- `POST /api/admin/login` — autenticación
- `POST /api/admin/register-filters` — crear nodes/filters/attribute_definitions
- `POST /api/admin/import-products-batch` — insertar/actualizar productos
- `POST /api/admin/upload-images-batch` — subir imágenes blob
- `POST /api/admin/refresh-filters` — auto-aplicar filtros progresivos por entropía

Todos requieren header `X-Admin-Token` obtenido del login.

## Pipeline (ejemplo SICK, ya ejecutado)

### 1. Descargar el PDF al directorio del proyecto

Pon el PDF en el cwd del proyecto. NO se sube al repo (excluido en `.gitignore`).

### 2. Extraer texto a JSON

```python
import pypdf, json
r = pypdf.PdfReader('CATALOGO.pdf')
pages = [{'page': i+1, 'text': p.extract_text() or ''} for i, p in enumerate(r.pages)]
json.dump(pages, open('pdf_text.json', 'w', encoding='utf-8'), ensure_ascii=False)
```

### 3. Parsear productos del texto

`parse_sick_pdf.py` es el ejemplo. Adaptar las heurísticas según el patrón del PDF:

- Identificar el separador típico de variantes (ej: `TYPE-CODE 7-DIGIT-REF`)
- Extraer atributos del contexto (rango_mm, salida_tipo, conexión, ip_rating, etc.)
- Mapear a leaves de la taxonomía existente con `detect_leaf()`

Output: `<brand>_products.json` con array de productos compatibles con
`normalize_product()`.

### 4. Si hay leaves nuevos, registrarlos primero

```bash
curl -X POST .../api/admin/register-filters \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @<brand>_register_payload.json
```

Body típico:
```json
{
  "nodes": [{"id": "deteccion-posicionamiento.foo", "label": "Foo", "parent": "deteccion-posicionamiento", "is_leaf": true}],
  "definitions": {"<aid>": {"label": "...", "kind": "enum", "field": "..."}},
  "leaf_filters": {"<leaf_id>": ["<aid>", ...]}
}
```

### 5. Importar productos en lote

```bash
curl -X POST .../api/admin/import-products-batch \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @<brand>_products.json
```

Idempotente: usa upsert por `id`.

### 6. Extraer e importar imágenes

`extract_sick_images_v2.py` es el ejemplo. Estrategia:
- Para cada página, identificar la imagen "principal" (mayor área, ≥ 80×80 px)
- Mapear cada producto a la imagen de su página, con fallback a la imagen
  de la "familia" del modelo (prefijo del SKU antes del primer guión)

Genera `<brand>_images_payload.json`. Subir:

```bash
curl -X POST .../api/admin/upload-images-batch \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @<brand>_images_payload.json
```

El frontend renderiza vía `image_local: true` + endpoint blob
`/api/products/<id>/image`.

### 7. Aplicar filtros automáticamente

```bash
curl -X POST .../api/admin/refresh-filters \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"auto_apply": true, "min_score": 0.4, "min_products": 3}'
```

## Resultado típico

Para SICK:
- 240 páginas → 1,543 productos
- 9 hojas nuevas en taxonomía
- 222 filtros progresivos (61 hojas)
- 925/1543 productos con imagen blob (60%)
- 74 imágenes únicas (compartidas por familia)

## Marcas con catálogo PDF disponible

| Marca | Estado | Productos |
| --- | --- | --- |
| SICK | ✓ Procesado | 1,543 |
| Phoenix Contact | PDFs en `Catalogos Phoenix/` (no procesado) | — |
| ABB | Sin PDF | — |
| Otros | Sin PDF | — |

## Marcas accesibles vía web (sin PDF)

| Marca | Vía | Productos |
| --- | --- | --- |
| Unitronics | Sitemap + páginas series | 127 |
| Janitza | Página productos | 14 |
