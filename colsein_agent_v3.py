#!/usr/bin/env python3
"""
colsein_agent_v3.py - Backend Colsein con SQLite.

Comandos:
  init                          Crea/migra la base de datos
  import-json <archivo>         Importa productos desde JSON
  export-json <archivo>         Exporta productos a JSON (para el HTML)
  export-html <archivo.html>    Genera HTML completo con dataset embebido
  add-product                   Agrega 1 producto (interactivo)
  add-leaf <id> <label>         Agrega una categoría hoja nueva
  add-filter <leaf_id> <attr>   Agrega un filtro progresivo a una hoja
  stats                         Estadísticas
  refine                        Limpieza y validación
  scrape --brand <id>           Scraping real (requiere requests + bs4)
  serve [--port 8000]           Servidor Flask local (opcional)

Uso típico:
  python colsein_agent_v3.py init
  python colsein_agent_v3.py import-json mis_productos.json
  python colsein_agent_v3.py export-html colsein_app.html
  # Abre colsein_app.html en el navegador

Ubicación de archivos:
  - colsein.db (SQLite, fuente de verdad)
  - taxonomy_editable.json (jerarquía + filtros)
  - colsein_app.html (frontend)
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# Configuración
# ============================================================================
HERE = Path(__file__).parent.resolve()
# DATA_DIR alberga la BD, la taxonomía editable y el HTML regenerado.
# Por defecto = HERE (modo dev local). En Railway se pasa DATA_DIR=/data
# (volumen persistente) para que admin no pierda cambios entre redeploys.
DATA_DIR = Path(os.environ.get("DATA_DIR", HERE)).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "colsein.db"
TAX_PATH = DATA_DIR / "taxonomy_editable.json"
DEFAULT_HTML = DATA_DIR / "colsein_app.html"
DEFAULT_TEMPLATE = HERE / "colsein_app_template.html"
GENERATED_HTML = DATA_DIR / "colsein_app_v3.html"

# ============================================================================
# Schema SQLite
# ============================================================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              TEXT PRIMARY KEY,
    brand           TEXT NOT NULL,
    model           TEXT,
    name            TEXT NOT NULL,
    family          TEXT,
    leaf            TEXT NOT NULL,
    secondary_leaves TEXT,        -- JSON array
    description     TEXT,
    manufacturer_url TEXT,
    datasheet_url   TEXT,
    image_url       TEXT,         -- URL externa primaria
    image_blob      BLOB,         -- respaldo local binario
    image_mime      TEXT,         -- 'image/jpeg', 'image/png', etc
    image_status    TEXT DEFAULT 'none',  -- none|url_ok|url_broken|blob_only
    image_checked_at TIMESTAMP,
    lifecycle       TEXT DEFAULT 'active',
    is_software     INTEGER DEFAULT 0,
    attributes      TEXT,         -- JSON object con todos los atributos planos
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_products_leaf ON products(leaf);
CREATE INDEX IF NOT EXISTS idx_products_image_status ON products(image_status);

CREATE TABLE IF NOT EXISTS load_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation   TEXT NOT NULL,    -- import|scrape|update|refine|export|images
    target      TEXT,             -- marca o archivo
    items       INTEGER DEFAULT 0,
    notes       TEXT,
    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Migraciones para BD existente (idempotentes)
MIGRATIONS = [
    "ALTER TABLE products ADD COLUMN image_url TEXT",
    "ALTER TABLE products ADD COLUMN image_blob BLOB",
    "ALTER TABLE products ADD COLUMN image_mime TEXT",
    "ALTER TABLE products ADD COLUMN image_status TEXT DEFAULT 'none'",
    "ALTER TABLE products ADD COLUMN image_checked_at TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS idx_products_image_status ON products(image_status)",
]


def apply_migrations(conn):
    """Aplica migraciones idempotentes para BD existentes."""
    applied = 0
    for stmt in MIGRATIONS:
        try:
            conn.execute(stmt)
            applied += 1
        except sqlite3.OperationalError as e:
            # columna ya existe, ignorar
            if "duplicate column" not in str(e).lower():
                pass
    if applied > 0:
        conn.commit()
    return applied

# ============================================================================
# Helpers DB
# ============================================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def log_operation(conn, operation, target=None, items=0, notes=None):
    conn.execute(
        "INSERT INTO load_log (operation, target, items, notes) VALUES (?, ?, ?, ?)",
        (operation, target, items, notes),
    )


def load_taxonomy():
    if not TAX_PATH.exists():
        die(f"No existe {TAX_PATH}. Crea el archivo o ejecuta 'init' con --create-tax.")
    with open(TAX_PATH, encoding="utf-8") as f:
        return json.load(f)


def die(msg, code=1):
    print(f"\033[31mERROR:\033[0m {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg):
    print(f"\033[34m›\033[0m {msg}")


def ok(msg):
    print(f"\033[32m✓\033[0m {msg}")


def warn(msg):
    print(f"\033[33m⚠\033[0m {msg}")


# ============================================================================
# Comando: init
# ============================================================================
def cmd_init(args):
    """Crea la base de datos si no existe, y aplica migraciones si es vieja."""
    new_db = not DB_PATH.exists()
    conn = get_db()
    conn.executescript(SCHEMA)
    n_mig = apply_migrations(conn)
    conn.commit()
    if new_db:
        ok(f"Base de datos creada: {DB_PATH}")
    else:
        info(f"Base de datos ya existe: {DB_PATH}")
        if n_mig:
            ok(f"  Migraciones aplicadas: {n_mig}")
    if not TAX_PATH.exists():
        warn(f"No existe {TAX_PATH}. Cópialo del repositorio o crea uno con add-leaf.")
    else:
        tax = load_taxonomy()
        ok(f"Taxonomía: {len(tax['nodes'])} nodos, {len(tax['leaf_filters'])} hojas con filtros")
    cnt = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    n_with_img = conn.execute("SELECT COUNT(*) FROM products WHERE image_url IS NOT NULL OR image_blob IS NOT NULL").fetchone()[0]
    ok(f"Productos en BD: {cnt} ({n_with_img} con imagen)")
    conn.close()


# ============================================================================
# Comando: import-json
# ============================================================================
def cmd_import_json(args):
    """Importa productos desde un archivo JSON.

    El JSON puede tener uno de estos formatos:
      1) Array directo: [{producto1}, {producto2}, ...]
      2) Objeto con productos: {"products": [...]}
      3) Formato del HTML: {"products_initial": [...], "products_remaining": [...]}
    """
    path = Path(args.archivo)
    if not path.exists():
        die(f"No existe el archivo: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Detectar formato
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "products" in data:
            items = data["products"]
        elif "products_initial" in data:
            items = data.get("products_initial", []) + data.get("products_remaining", [])
        else:
            die("JSON no reconocido. Usa array, {products: [...]} o el export del HTML.")
    else:
        die("Formato JSON inválido")

    info(f"Procesando {len(items)} productos de {path.name}")

    conn = get_db()
    inserted = updated = skipped = 0
    for raw in items:
        p = normalize_product(raw)
        if not p:
            skipped += 1
            continue
        existing = conn.execute("SELECT id FROM products WHERE id = ?", (p["id"],)).fetchone()
        if existing and not args.replace:
            skipped += 1
            continue
        if existing:
            conn.execute("""UPDATE products SET
                brand=?, model=?, name=?, family=?, leaf=?, secondary_leaves=?,
                description=?, manufacturer_url=?, datasheet_url=?, image_url=?,
                lifecycle=?, is_software=?, attributes=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (p["brand"], p["model"], p["name"], p["family"], p["leaf"],
                 json.dumps(p["secondary_leaves"]), p["description"], p["manufacturer_url"],
                 p["datasheet_url"], p.get("image_url"), p["lifecycle"], p["is_software"],
                 json.dumps(p["attributes"]), p["id"]))
            updated += 1
        else:
            conn.execute("""INSERT INTO products
                (id, brand, model, name, family, leaf, secondary_leaves,
                 description, manufacturer_url, datasheet_url, image_url,
                 lifecycle, is_software, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["id"], p["brand"], p["model"], p["name"], p["family"], p["leaf"],
                 json.dumps(p["secondary_leaves"]), p["description"], p["manufacturer_url"],
                 p["datasheet_url"], p.get("image_url"), p["lifecycle"], p["is_software"],
                 json.dumps(p["attributes"])))
            inserted += 1

    log_operation(conn, "import", str(path.name), inserted + updated,
                  f"{inserted} nuevos, {updated} actualizados, {skipped} omitidos")
    conn.commit()
    conn.close()
    ok(f"Importados: {inserted} nuevos, {updated} actualizados, {skipped} omitidos")


def normalize_product(raw):
    """Normaliza un producto crudo (de JSON externo o del HTML compactado)
    al formato canónico de la BD."""
    # Detectar formato compactado vs completo
    if "product_id" in raw:
        # formato completo (con campo "attributes" anidado)
        attrs = raw.get("attributes", {}) or {}
        return {
            "id": raw["product_id"],
            "brand": raw["brand_id"],
            "model": raw.get("model_number", ""),
            "name": raw["product_name"],
            "family": raw.get("family"),
            "leaf": raw["primary_leaf_node_id"],
            "secondary_leaves": raw.get("secondary_leaf_node_ids", []) or [],
            "description": raw.get("short_description", "") or "",
            "manufacturer_url": raw.get("manufacturer_url"),
            "datasheet_url": (raw.get("datasheet_urls") or [{}])[0].get("url")
                              if raw.get("datasheet_urls") else None,
            "image_url": raw.get("image_url") or attrs.get("image_url"),
            "lifecycle": attrs.get("lifecycle_status", "active"),
            "is_software": 1 if attrs.get("is_software") else 0,
            "attributes": {k: v for k, v in attrs.items()
                           if k not in ("lifecycle_status", "is_software", "image_url")},
        }
    # Formato compactado (del HTML)
    if "id" in raw and "leaf" in raw:
        # Reconstruir attributes desde campos planos
        meta_keys = {"id", "brand", "model", "name", "family", "leaf",
                     "secondary_leaves", "desc", "url", "datasheet", "image_url",
                     "lifecycle", "is_software"}
        attrs = {k: v for k, v in raw.items() if k not in meta_keys}
        return {
            "id": raw["id"],
            "brand": raw["brand"],
            "model": raw.get("model", ""),
            "name": raw["name"],
            "family": raw.get("family"),
            "leaf": raw["leaf"],
            "secondary_leaves": raw.get("secondary_leaves", []) or [],
            "description": raw.get("desc", "") or "",
            "manufacturer_url": raw.get("url"),
            "datasheet_url": raw.get("datasheet"),
            "image_url": raw.get("image_url"),
            "lifecycle": raw.get("lifecycle", "active"),
            "is_software": 1 if raw.get("is_software") else 0,
            "attributes": attrs,
        }
    return None


# ============================================================================
# Comando: export-json
# ============================================================================
def cmd_export_json(args):
    """Exporta toda la BD a JSON (formato compactado, listo para el HTML)."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM products ORDER BY brand, leaf, model").fetchall()
    products = [row_to_compact(r) for r in rows]

    tax = load_taxonomy()

    # Split inicial / remaining: 2 por marca para inicial
    from collections import defaultdict
    by_brand = defaultdict(list)
    for p in products:
        by_brand[p["brand"]].append(p)
    initial_ids = set()
    initial = []
    for bid in sorted(by_brand):
        for p in by_brand[bid][:2]:
            initial.append(p)
            initial_ids.add(p["id"])
    remaining = [p for p in products if p["id"] not in initial_ids]

    out = {
        "stats": {
            "total_products": len(products),
            "total_brands": len(tax["brands"]),
            "total_leaves": sum(1 for n in tax["nodes"] if n.get("is_leaf")),
            "initial_loaded": len(initial),
            "remaining_to_load": len(remaining),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "brands": tax["brands"],
        "taxonomy": tax["nodes"],
        "attribute_definitions": tax["attribute_definitions"],
        "leaf_filters": tax["leaf_filters"],
        "universal_filters": tax["universal_filters"],
        "products_initial": initial,
        "products_remaining": remaining,
    }

    path = Path(args.archivo)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    log_operation(conn, "export", str(path.name), len(products))
    conn.commit()
    conn.close()
    sz = os.path.getsize(path)
    ok(f"Exportado a {path} ({sz/1024:.1f} KB) · {len(products)} productos")


def row_to_compact(row):
    """Convierte una fila de SQLite al formato compactado del HTML."""
    attrs = json.loads(row["attributes"] or "{}")
    secondary = json.loads(row["secondary_leaves"] or "[]")
    out = {
        "id": row["id"], "brand": row["brand"], "model": row["model"] or "",
        "name": row["name"], "family": row["family"], "leaf": row["leaf"],
    }
    if secondary: out["secondary_leaves"] = secondary
    if row["description"]: out["desc"] = row["description"]
    if row["manufacturer_url"]: out["url"] = row["manufacturer_url"]
    if row["datasheet_url"]: out["datasheet"] = row["datasheet_url"]
    # Imagen: prioridad URL, fallback a endpoint /api/products/<id>/image (cuando hay blob)
    try:
        has_blob = row["image_blob"] is not None
    except (KeyError, IndexError):
        has_blob = False
    if row["image_url"]:
        out["image_url"] = row["image_url"]
    if has_blob:
        out["image_local"] = True  # señal al HTML de que hay respaldo local
    if row["lifecycle"] and row["lifecycle"] != "active":
        out["lifecycle"] = row["lifecycle"]
    if row["is_software"]:
        out["is_software"] = True
    # Aplanar atributos: remover null/empty
    for k, v in attrs.items():
        if v is not None and v != "" and v != [] and v is not False:
            out[k] = v
    return out


# ============================================================================
# Comando: stats
# ============================================================================
def cmd_stats(args):
    """Muestra estadísticas de la BD."""
    conn = get_db()
    cnt = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    print(f"\n{'═'*50}")
    print(f"  ESTADÍSTICAS COLSEIN")
    print(f"{'═'*50}\n")
    print(f"Productos totales:    {cnt}")
    print(f"Base de datos:        {DB_PATH}")

    # Por marca
    print(f"\nPor marca:")
    rows = conn.execute("""SELECT brand, COUNT(*) as n FROM products
                           GROUP BY brand ORDER BY n DESC""").fetchall()
    for r in rows:
        bar = "█" * min(20, r["n"] // 2)
        print(f"  {r['brand']:20s} {r['n']:4d}  {bar}")

    # Hojas más densas
    print(f"\nTop 10 categorías más pobladas:")
    rows = conn.execute("""SELECT leaf, COUNT(*) as n FROM products
                           GROUP BY leaf ORDER BY n DESC LIMIT 10""").fetchall()
    for r in rows:
        print(f"  {r['n']:4d}  {r['leaf']}")

    # Operaciones recientes
    print(f"\nÚltimas 5 operaciones:")
    rows = conn.execute("""SELECT operation, target, items, timestamp FROM load_log
                           ORDER BY timestamp DESC LIMIT 5""").fetchall()
    for r in rows:
        print(f"  {r['timestamp']}  {r['operation']:8s}  {r['target'] or '':30s}  {r['items']} items")
    print()
    conn.close()


# ============================================================================
# Comando: add-product (interactivo)
# ============================================================================
def cmd_add_product(args):
    """Agrega un producto interactivamente."""
    tax = load_taxonomy()
    leaves = [n for n in tax["nodes"] if n.get("is_leaf")]

    print("\n" + "═"*50)
    print("  AGREGAR PRODUCTO")
    print("═"*50 + "\n")

    brand = ask_choice("Marca", [b["id"] for b in tax["brands"]])
    print()
    print(f"Categorías hoja disponibles ({len(leaves)}):")
    for i, l in enumerate(leaves[:30]):
        print(f"  [{i:3d}] {l['id']}")
    if len(leaves) > 30:
        print(f"  ... y {len(leaves)-30} más. Escribe el id directamente.")
    leaf = input("\nCategoría (id o número): ").strip()
    if leaf.isdigit():
        leaf = leaves[int(leaf)]["id"]
    if not any(l["id"] == leaf for l in leaves):
        die(f"Categoría no válida: {leaf}")

    model = input("Modelo: ").strip()
    name = input("Nombre del producto: ").strip()
    desc = input("Descripción corta: ").strip()
    url = input("URL fabricante (enter para omitir): ").strip() or None
    pid = f"{brand}-{model.lower().replace(' ','-').replace('/','-')}"

    # Filtros declarados para esta hoja → preguntar valores
    attrs = {}
    leaf_filters = tax["leaf_filters"].get(leaf, [])
    if leaf_filters:
        print(f"\nFiltros declarados para esta hoja ({len(leaf_filters)}):")
        for f in leaf_filters:
            attr_def = tax["attribute_definitions"].get(f["id"])
            if not attr_def:
                continue
            label = attr_def.get("label", f["id"])
            v = input(f"  {label} [{f['id']}] (enter omite): ").strip()
            if v:
                attrs[attr_def["field"]] = v

    # Industrias y certificaciones (universales)
    inds = input("Industrias (separadas por coma, enter omite): ").strip()
    if inds:
        attrs["industries"] = [x.strip() for x in inds.split(",")]
    certs = input("Certificaciones (CE,UL,...): ").strip()
    if certs:
        attrs["certs"] = [x.strip() for x in certs.split(",")]

    # Insertar
    conn = get_db()
    try:
        conn.execute("""INSERT INTO products
            (id, brand, model, name, family, leaf, description,
             manufacturer_url, lifecycle, is_software, attributes,
             secondary_leaves)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, '[]')""",
            (pid, brand, model, name, None, leaf, desc, url,
             json.dumps(attrs)))
        log_operation(conn, "import", "manual", 1, f"Producto {pid}")
        conn.commit()
        ok(f"Producto agregado: {pid}")
    except sqlite3.IntegrityError:
        die(f"Ya existe un producto con ID {pid}. Usa import-json --replace para sobrescribir.")
    conn.close()


def ask_choice(prompt, options):
    """Pregunta una opción de una lista."""
    print(f"{prompt}: {', '.join(options[:10])}{'...' if len(options) > 10 else ''}")
    while True:
        v = input(f"  > ").strip()
        if v in options:
            return v
        print(f"  Opción inválida. Disponibles: {', '.join(options)}")


# ============================================================================
# Comando: add-leaf (agregar categoría hoja)
# ============================================================================
def cmd_add_leaf(args):
    """Agrega una hoja nueva a la taxonomía."""
    tax = load_taxonomy()
    if any(n["id"] == args.leaf_id for n in tax["nodes"]):
        die(f"Ya existe nodo con id {args.leaf_id}")
    parent_id = ".".join(args.leaf_id.split(".")[:-1]) or None
    if parent_id and not any(n["id"] == parent_id for n in tax["nodes"]):
        die(f"No existe nodo padre {parent_id}. Crea primero los nodos intermedios.")
    new_node = {
        "id": args.leaf_id,
        "label": args.label,
        "parent": parent_id,
        "is_leaf": True,
        "level": args.leaf_id.count(".") + 1,
        "trunk": args.leaf_id.split(".")[0],
    }
    tax["nodes"].append(new_node)
    tax["leaf_filters"].setdefault(args.leaf_id, [])
    TAX_PATH.write_text(json.dumps(tax, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"Hoja agregada: {args.leaf_id} ({args.label})")
    info(f"Edita {TAX_PATH} para agregar filtros progresivos a esta hoja.")


# ============================================================================
# Comando: add-filter (agregar filtro a hoja)
# ============================================================================
def cmd_add_filter(args):
    """Agrega un filtro progresivo a una hoja existente."""
    tax = load_taxonomy()
    if args.leaf_id not in tax["leaf_filters"]:
        # crear lista vacía si la hoja existe
        if not any(n["id"] == args.leaf_id for n in tax["nodes"]):
            die(f"No existe hoja {args.leaf_id}")
        tax["leaf_filters"][args.leaf_id] = []
    if args.attribute_id not in tax["attribute_definitions"]:
        die(f"Atributo no definido: {args.attribute_id}. Agrégalo primero a 'attribute_definitions' en {TAX_PATH}")
    if any(f["id"] == args.attribute_id for f in tax["leaf_filters"][args.leaf_id]):
        warn(f"El filtro ya existe en esta hoja")
        return
    tax["leaf_filters"][args.leaf_id].append({"id": args.attribute_id})
    TAX_PATH.write_text(json.dumps(tax, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"Filtro agregado: {args.attribute_id} → {args.leaf_id}")


# ============================================================================
# Comando: refine
# ============================================================================
def cmd_refine(args):
    """Limpieza y validación de la BD."""
    conn = get_db()
    issues = 0

    # 1) Normalizar certificaciones
    info("Normalizando certificaciones…")
    syn = {"atex":"ATEX","iecex":"IECEx","ce":"CE","ul":"UL","csa":"CSA",
           "fcc":"FCC","rohs":"RoHS","sil2":"SIL2","sil3":"SIL3"}
    rows = conn.execute("SELECT id, attributes FROM products").fetchall()
    fixed = 0
    for r in rows:
        attrs = json.loads(r["attributes"] or "{}")
        if not attrs.get("certs"):
            continue
        new_certs = []
        changed = False
        for c in attrs["certs"]:
            k = c.lower().replace(" ","").replace("_","").replace("-","")
            if k in syn and syn[k] != c:
                new_certs.append(syn[k])
                changed = True
            else:
                new_certs.append(c)
        if changed:
            attrs["certs"] = new_certs
            conn.execute("UPDATE products SET attributes=? WHERE id=?",
                         (json.dumps(attrs), r["id"]))
            fixed += 1
    if fixed:
        ok(f"  {fixed} productos con certificaciones normalizadas")
        issues += fixed

    # 2) Detectar duplicados marca+modelo
    info("Buscando duplicados marca+modelo…")
    rows = conn.execute("""SELECT brand || '|' || LOWER(REPLACE(model, ' ', '')) as key,
                           GROUP_CONCAT(id) as ids, COUNT(*) as n
                           FROM products WHERE model != '' GROUP BY key HAVING n > 1""").fetchall()
    if rows:
        warn(f"  {len(rows)} grupos de duplicados:")
        for r in rows[:5]:
            print(f"    {r['key']}: {r['ids']}")
        issues += len(rows)
    else:
        ok("  Sin duplicados")

    # 3) Productos sin descripción
    cnt = conn.execute("SELECT COUNT(*) FROM products WHERE description IS NULL OR description = ''").fetchone()[0]
    if cnt:
        warn(f"  {cnt} productos sin descripción")

    log_operation(conn, "refine", None, issues, f"{fixed} normalizados, {len(rows) if rows else 0} dups")
    conn.commit()
    conn.close()


# ============================================================================
# Comando: download-images (descarga URLs a blobs locales como respaldo)
# ============================================================================
def cmd_download_images(args):
    """Descarga las image_url al disco como blob en SQLite (respaldo local).

    Por defecto sólo descarga las que aún no tienen blob.
    Con --recheck también revalida las que ya están como url_broken.
    """
    try:
        import requests
    except ImportError:
        die("Instala dependencias: pip install requests")

    conn = get_db()
    apply_migrations(conn)

    if args.recheck:
        rows = conn.execute(
            "SELECT id, image_url, image_status FROM products "
            "WHERE image_url IS NOT NULL"
        ).fetchall()
    elif args.brand:
        rows = conn.execute(
            "SELECT id, image_url, image_status FROM products "
            "WHERE image_url IS NOT NULL AND image_blob IS NULL AND brand = ?",
            (args.brand,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, image_url, image_status FROM products "
            "WHERE image_url IS NOT NULL AND image_blob IS NULL"
        ).fetchall()

    if args.limit:
        rows = rows[: args.limit]

    info(f"Descargando imágenes de {len(rows)} productos…")
    if not rows:
        ok("No hay imágenes pendientes de descargar")
        conn.close()
        return

    session = requests.Session()
    session.headers["User-Agent"] = SCRAPER_USER_AGENT

    ok_count = fail_count = skipped = 0
    for i, r in enumerate(rows, 1):
        url = r["image_url"]
        pid = r["id"]
        if i % 25 == 0 or i == len(rows):
            print(f"  [{i}/{len(rows)}] última: {pid}")
        try:
            time.sleep(SCRAPER_RATE_LIMIT)
            resp = session.get(url, timeout=20, stream=True)
            if resp.status_code != 200:
                conn.execute(
                    "UPDATE products SET image_status='url_broken', image_checked_at=CURRENT_TIMESTAMP WHERE id=?",
                    (pid,))
                fail_count += 1
                continue
            content = resp.content
            if len(content) > 5 * 1024 * 1024:  # >5MB sospechoso, omitir
                skipped += 1
                continue
            mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            if not mime.startswith("image/"):
                conn.execute(
                    "UPDATE products SET image_status='url_broken', image_checked_at=CURRENT_TIMESTAMP WHERE id=?",
                    (pid,))
                fail_count += 1
                continue
            conn.execute(
                "UPDATE products SET image_blob=?, image_mime=?, image_status='url_ok', "
                "image_checked_at=CURRENT_TIMESTAMP WHERE id=?",
                (content, mime, pid))
            ok_count += 1
            if ok_count % 10 == 0:
                conn.commit()  # commit periódico
        except Exception as e:
            conn.execute(
                "UPDATE products SET image_status='url_broken', image_checked_at=CURRENT_TIMESTAMP WHERE id=?",
                (pid,))
            fail_count += 1
    log_operation(conn, "images", args.brand, ok_count,
                  f"{ok_count} ok, {fail_count} fallidas, {skipped} omitidas")
    conn.commit()
    conn.close()
    ok(f"Descargadas: {ok_count}, fallidas: {fail_count}, omitidas: {skipped}")
    if fail_count:
        info("Las URLs rotas quedaron marcadas como 'url_broken'. "
             "Puedes corregirlas manualmente y re-correr download-images --recheck")


# ============================================================================
# Comando: set-image (asignar imagen manual a un producto)
# ============================================================================
def cmd_set_image(args):
    """Asigna una imagen a un producto, ya sea desde URL o archivo local."""
    conn = get_db()
    apply_migrations(conn)
    row = conn.execute("SELECT id FROM products WHERE id = ?", (args.product_id,)).fetchone()
    if not row:
        die(f"No existe producto con id {args.product_id}")

    if args.url:
        conn.execute(
            "UPDATE products SET image_url=?, image_status='none' WHERE id=?",
            (args.url, args.product_id))
        ok(f"URL asignada a {args.product_id}")
    if args.file:
        path = Path(args.file)
        if not path.exists():
            die(f"No existe archivo: {path}")
        ext = path.suffix.lower().lstrip(".")
        mime_map = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
                    "webp":"image/webp","gif":"image/gif"}
        mime = mime_map.get(ext)
        if not mime:
            die(f"Extensión no soportada: {ext}")
        with open(path, "rb") as f:
            blob = f.read()
        conn.execute(
            "UPDATE products SET image_blob=?, image_mime=?, image_status='blob_only', "
            "image_checked_at=CURRENT_TIMESTAMP WHERE id=?",
            (blob, mime, args.product_id))
        ok(f"Imagen local cargada en {args.product_id} ({len(blob)//1024} KB, {mime})")
    if not args.url and not args.file:
        die("Debes especificar --url o --file")
    conn.commit()
    conn.close()


# ============================================================================
# Comando: suggest-filters (analiza la BD y propone filtros nuevos)
# ============================================================================
def cmd_suggest_filters(args):
    """Analiza atributos por hoja y sugiere los más discriminantes
    que no están aún declarados como filtros."""
    conn = get_db()
    tax = load_taxonomy()
    declared = tax["leaf_filters"]
    universal_ids = {f["id"] for f in tax["universal_filters"]}
    attr_defs = tax.get("attribute_definitions", {})
    # field -> attribute_id (inverso)
    field_to_attr = {d["field"]: aid for aid, d in attr_defs.items()}
    # también atributo_id directo (cuando el field name == attr_id)
    attr_id_set = set(attr_defs.keys())

    # Agrupar productos por hoja
    rows = conn.execute(
        "SELECT leaf, attributes FROM products WHERE leaf != 'needs_classification'"
    ).fetchall()
    by_leaf = {}
    for r in rows:
        leaf = r["leaf"]
        attrs = json.loads(r["attributes"] or "{}")
        by_leaf.setdefault(leaf, []).append(attrs)
    conn.close()

    # Filtrar hojas con >=5 productos (umbral para discriminar)
    candidates = {l: ps for l, ps in by_leaf.items() if len(ps) >= args.min_products}

    info(f"Hojas con ≥{args.min_products} productos: {len(candidates)}")
    print()

    suggestions = []
    for leaf in sorted(candidates):
        products = candidates[leaf]
        n = len(products)
        # contar valores por field
        field_counts = {}  # field -> {value: count}
        for p in products:
            for f, v in p.items():
                if v is None or v == "" or v == [] or v is False:
                    continue
                field_counts.setdefault(f, {})
                if isinstance(v, list):
                    for x in v:
                        key = str(x)
                        field_counts[f][key] = field_counts[f].get(key, 0) + 1
                else:
                    key = str(v)
                    field_counts[f][key] = field_counts[f].get(key, 0) + 1

        # ya declarados
        declared_attr_ids = {f["id"] for f in declared.get(leaf, [])}
        # los fields correspondientes a los declarados
        declared_fields = set()
        for aid in declared_attr_ids:
            if aid in attr_defs:
                declared_fields.add(attr_defs[aid]["field"])
            declared_fields.add(aid)  # también el propio attr_id, por si el field == attr_id

        # poder discriminante = entropía normalizada * cobertura
        scored = []
        for field, counts in field_counts.items():
            # un field "ya está declarado" si es declared_field o si es attr_id de uno declarado
            if field in declared_fields or field in declared_attr_ids:
                continue
            if field in universal_ids:
                continue
            distinct = len(counts)
            if distinct < 2 or distinct > n * 0.8:
                continue
            coverage = sum(counts.values()) / n
            if coverage < 0.4:
                continue
            import math
            total = sum(counts.values())
            entropy = -sum((c/total) * math.log2(c/total) for c in counts.values())
            max_entropy = math.log2(distinct)
            normalized = entropy / max_entropy if max_entropy > 0 else 0
            score = normalized * coverage * (1 if 2 <= distinct <= 8 else 0.5)
            # determinar attr_id correspondiente: 1) field es field de un attr, 2) field es attr_id directo
            attr_id = field_to_attr.get(field) or (field if field in attr_id_set else None)
            scored.append({
                "field": field,
                "attr_id": attr_id,
                "distinct_values": distinct,
                "coverage": round(coverage * 100, 1),
                "score": round(score, 3),
                "sample_values": list(counts.keys())[:6],
            })
        scored.sort(key=lambda x: -x["score"])
        if not scored:
            continue
        suggestions.append({"leaf": leaf, "n_products": n, "candidates": scored[:args.top]})

    # Mostrar resultados
    if not suggestions:
        warn("No se encontraron sugerencias. Necesitas más productos por hoja con datos en sus atributos.")
        return

    print("=" * 70)
    print("  FILTROS SUGERIDOS")
    print("=" * 70)
    for s in suggestions[: args.max_leaves]:
        print(f"\n• {s['leaf']}  ({s['n_products']} productos)")
        already = [f["id"] for f in declared.get(s["leaf"], [])]
        if already:
            print(f"  Ya declarados: {', '.join(already)}")
        for c in s["candidates"]:
            attr_marker = c["attr_id"] or f"⚠ field '{c['field']}' sin definir en attribute_definitions"
            print(f"    {c['score']:.2f}  {c['field']:30s}  ({c['distinct_values']} valores · cobertura {c['coverage']}%)")
            print(f"          → atributo: {attr_marker}")
            print(f"          → valores: {', '.join(c['sample_values'][:5])}")

    print()
    print("=" * 70)
    print("  CÓMO APLICAR (manual o pidiéndole a Claude Code)")
    print("=" * 70)
    print("""
Para cada sugerencia que te convenza:

1. Si el atributo NO está en attribute_definitions de taxonomy_editable.json,
   agrégalo con:
   {
     "<attribute_id>": {
       "label": "<etiqueta legible>",
       "kind": "enum",  // o "enum_multi" si es lista
       "field": "<field_name>"
     }
   }

2. Conecta el atributo a la hoja:
   python3 colsein_agent_v3.py add-filter <leaf_id> <attribute_id>

3. Regenera el HTML:
   python3 colsein_agent_v3.py export-html colsein_app_v3.html
""")

    # Si hay output a archivo, generar un prompt listo para Claude Code
    if args.output:
        prompt = generate_claude_code_prompt(suggestions, attr_defs)
        Path(args.output).write_text(prompt, encoding="utf-8")
        ok(f"Prompt para Claude Code guardado en: {args.output}")


def generate_claude_code_prompt(suggestions, attr_defs):
    """Genera un prompt en español para que Claude Code aplique las sugerencias."""
    lines = [
        "# Tarea: agregar filtros progresivos al catálogo Colsein",
        "",
        "Edita `taxonomy_editable.json` para agregar los filtros progresivos sugeridos a continuación.",
        "Para cada filtro:",
        "1. Si el campo no existe en `attribute_definitions`, agrégalo con su label, kind y field",
        "2. Agrega el `{\"id\": \"<attribute_id>\"}` al array `leaf_filters[<hoja>]`",
        "",
        "Reglas:",
        "- `kind: \"enum\"` para un solo valor por producto, `kind: \"enum_multi\"` si es lista",
        "- El `field` debe coincidir EXACTAMENTE con la clave plana en los productos",
        "- No dupliques filtros que ya estén declarados",
        "",
        "## Sugerencias automáticas (basadas en análisis de datos)",
        "",
    ]
    for s in suggestions:
        lines.append(f"### {s['leaf']} ({s['n_products']} productos)")
        for c in s["candidates"][:5]:
            attr_id = c["attr_id"] or f"<inventa-id-para-{c['field']}>"
            existing = c["field"] in [d["field"] for d in attr_defs.values()]
            kind_hint = "enum_multi" if any("," in str(v) for v in c["sample_values"]) else "enum"
            lines.append(f"- **{c['field']}** → score {c['score']:.2f}, {c['distinct_values']} valores distintos, cobertura {c['coverage']}%")
            lines.append(f"  - Sugerido attribute_id: `{attr_id}`")
            lines.append(f"  - Valores típicos: {', '.join(c['sample_values'][:5])}")
            lines.append(f"  - {'Ya definido' if existing else 'Falta definir en attribute_definitions'} (kind: {kind_hint})")
        lines.append("")
    lines.append("Después aplica con:")
    lines.append("```bash")
    lines.append("python3 colsein_agent_v3.py export-html colsein_app_v3.html")
    lines.append("```")
    return "\n".join(lines)


# ============================================================================
# Comando: export-html
# ============================================================================
def cmd_export_html(args):
    """Genera el HTML completo con dataset embebido (autosuficiente, offline)."""
    template_path = Path(args.template) if args.template else DEFAULT_TEMPLATE
    if not template_path.exists():
        die(f"No existe el template HTML: {template_path}\n"
            f"Coloca colsein_app_template.html (con placeholder __DATA_JSON__) en este directorio")

    template = template_path.read_text(encoding="utf-8")
    if "__DATA_JSON__" not in template:
        die(f"El template no contiene el placeholder __DATA_JSON__")

    # Generar dataset (mismo que export-json pero en memoria)
    conn = get_db()
    rows = conn.execute("SELECT * FROM products ORDER BY brand, leaf, model").fetchall()
    products = [row_to_compact(r) for r in rows]
    tax = load_taxonomy()

    from collections import defaultdict
    by_brand = defaultdict(list)
    for p in products:
        by_brand[p["brand"]].append(p)
    initial_ids = set()
    initial = []
    for bid in sorted(by_brand):
        for p in by_brand[bid][:2]:
            initial.append(p)
            initial_ids.add(p["id"])
    remaining = [p for p in products if p["id"] not in initial_ids]

    data = {
        "stats": {
            "total_products": len(products),
            "total_brands": len(tax["brands"]),
            "total_leaves": sum(1 for n in tax["nodes"] if n.get("is_leaf")),
            "initial_loaded": len(initial),
            "remaining_to_load": len(remaining),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "brands": tax["brands"],
        "taxonomy": tax["nodes"],
        "attribute_definitions": tax["attribute_definitions"],
        "leaf_filters": tax["leaf_filters"],
        "universal_filters": tax["universal_filters"],
        "products_initial": initial,
        "products_remaining": remaining,
    }
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("</script>", "<\\/script>")

    final = template.replace("__DATA_JSON__", data_json)
    out = Path(args.archivo)
    out.write_text(final, encoding="utf-8")

    log_operation(conn, "export", str(out.name), len(products))
    conn.commit()
    conn.close()

    sz = os.path.getsize(out)
    ok(f"HTML generado: {out} ({sz/1024:.1f} KB)")
    info(f"Ábrelo con doble clic en cualquier navegador (funciona offline).")


# ============================================================================
# Comando: scrape (real, con rate limit)
# ============================================================================
SCRAPER_USER_AGENT = "ColseinAgent/3.0 (+https://colsein.com.co)"
SCRAPER_RATE_LIMIT = 1.0  # segundos entre requests

def cmd_scrape(args):
    """Scraping real de productos del fabricante."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        die("Instala dependencias: pip install requests beautifulsoup4 lxml")

    tax = load_taxonomy()
    brand_info = next((b for b in tax["brands"] if b["id"] == args.brand), None)
    if not brand_info:
        die(f"Marca no reconocida: {args.brand}. Marcas válidas: {[b['id'] for b in tax['brands']]}")

    info(f"Iniciando scraping de {brand_info['name']} (límite: {args.batch} productos)")
    info(f"User-Agent: {SCRAPER_USER_AGENT}")
    info(f"Rate limit: {SCRAPER_RATE_LIMIT}s entre requests")

    session = requests.Session()
    session.headers["User-Agent"] = SCRAPER_USER_AGENT

    base_url = brand_info.get("url")
    if not base_url:
        die(f"La marca {args.brand} no tiene URL configurada en taxonomy_editable.json")

    # Scraper genérico: bajar la home, buscar enlaces que parezcan productos
    info(f"GET {base_url}")
    try:
        r = session.get(base_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        die(f"Error al conectar: {e}")

    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(k in href.lower() for k in ["/product", "/products/", "/p/", "/catalog"]):
            if href.startswith("/"):
                href = base_url.rstrip("/") + href
            elif not href.startswith("http"):
                continue
            links.append((href, a.get_text(strip=True)[:80]))
    links = list(dict.fromkeys(links))[:args.batch]

    info(f"Enlaces candidatos: {len(links)}")
    if not links:
        warn("No se encontraron enlaces de productos. La estructura del sitio puede haber cambiado.")
        warn("Recomendación: usa import-json con un archivo generado por Claude AI a partir del catálogo.")
        return

    conn = get_db()
    inserted = 0
    for i, (url, label) in enumerate(links, 1):
        if i % 10 == 0:
            print(f"  [{i}/{len(links)}] {url[:70]}")
        time.sleep(SCRAPER_RATE_LIMIT)
        try:
            pr = session.get(url, timeout=30)
            if pr.status_code != 200:
                continue
            psoup = BeautifulSoup(pr.text, "html.parser")
            title = (psoup.find("h1") or psoup.find("title"))
            title = title.get_text(strip=True)[:200] if title else label
            if not title:
                continue
            pid = f"{args.brand}-scraped-{hash(url) & 0xFFFFFF:06x}"
            try:
                conn.execute("""INSERT INTO products
                    (id, brand, model, name, leaf, description, manufacturer_url,
                     lifecycle, is_software, attributes, secondary_leaves)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, '{}', '[]')""",
                    (pid, args.brand, "", title, "needs_classification",
                     label or "", url))
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        except Exception as e:
            warn(f"  Error en {url}: {e}")
            continue

    log_operation(conn, "scrape", args.brand, inserted)
    conn.commit()
    conn.close()
    ok(f"Scraping completado: {inserted} productos nuevos en BD")
    info(f"Los productos quedaron en leaf='needs_classification'. Usa Claude AI para clasificarlos:")
    info(f"  python {Path(__file__).name} export-json sin_clasificar.json")
    info(f"  # Lleva ese JSON a Claude AI para que asigne leaf y atributos")
    info(f"  python {Path(__file__).name} import-json clasificado.json --replace")


# ============================================================================
# Helpers reutilizables (CLI + servidor admin)
# ============================================================================
def compute_filter_suggestions(tax, min_products=5, top=5):
    """Versión programática de cmd_suggest_filters que retorna estructura JSON.
    Comparte la misma lógica de scoring por entropía Shannon × cobertura."""
    import math
    declared = tax["leaf_filters"]
    universal_ids = {f["id"] for f in tax["universal_filters"]}
    attr_defs = tax.get("attribute_definitions", {})
    field_to_attr = {d["field"]: aid for aid, d in attr_defs.items()}
    attr_id_set = set(attr_defs.keys())

    conn = get_db()
    rows = conn.execute(
        "SELECT leaf, attributes FROM products WHERE leaf != 'needs_classification'"
    ).fetchall()
    conn.close()

    by_leaf = {}
    for r in rows:
        attrs = json.loads(r["attributes"] or "{}")
        by_leaf.setdefault(r["leaf"], []).append(attrs)

    candidates = {l: ps for l, ps in by_leaf.items() if len(ps) >= min_products}

    suggestions = []
    for leaf in sorted(candidates):
        products = candidates[leaf]
        n = len(products)
        field_counts = {}
        for p in products:
            for f, v in p.items():
                if v is None or v == "" or v == [] or v is False:
                    continue
                field_counts.setdefault(f, {})
                if isinstance(v, list):
                    for x in v:
                        key = str(x)
                        field_counts[f][key] = field_counts[f].get(key, 0) + 1
                else:
                    key = str(v)
                    field_counts[f][key] = field_counts[f].get(key, 0) + 1

        declared_attr_ids = {f["id"] for f in declared.get(leaf, [])}
        declared_fields = set()
        for aid in declared_attr_ids:
            if aid in attr_defs:
                declared_fields.add(attr_defs[aid]["field"])
            declared_fields.add(aid)

        scored = []
        for field, counts in field_counts.items():
            if field in declared_fields or field in declared_attr_ids:
                continue
            if field in universal_ids:
                continue
            distinct = len(counts)
            if distinct < 2 or distinct > n * 0.8:
                continue
            coverage = sum(counts.values()) / n
            if coverage < 0.4:
                continue
            total = sum(counts.values())
            entropy = -sum((c/total) * math.log2(c/total) for c in counts.values())
            max_entropy = math.log2(distinct)
            normalized = entropy / max_entropy if max_entropy > 0 else 0
            score = normalized * coverage * (1 if 2 <= distinct <= 8 else 0.5)
            attr_id = field_to_attr.get(field) or (field if field in attr_id_set else None)
            kind = "enum_multi" if any(isinstance(p.get(field), list) for p in products) else "enum"
            scored.append({
                "field": field,
                "attr_id": attr_id,
                "needs_definition": attr_id is None,
                "kind_hint": kind,
                "distinct_values": distinct,
                "coverage_pct": round(coverage * 100, 1),
                "score": round(score, 3),
                "sample_values": list(counts.keys())[:6],
            })
        scored.sort(key=lambda x: -x["score"])
        if scored:
            suggestions.append({
                "leaf": leaf,
                "n_products": n,
                "already_declared": list(declared_attr_ids),
                "candidates": scored[:top],
            })

    return suggestions


def apply_filter_suggestions(tax, suggestions, min_score=0.6):
    """Aplica sugerencias con score >= min_score directamente al objeto tax.
    Retorna (lista de aplicados, prompt_para_claude_code para los que no se pueden auto-aplicar).
    """
    applied = []
    needs_claude = []  # los que requieren definir attribute_definitions nuevos

    for s in suggestions:
        leaf = s["leaf"]
        for c in s["candidates"]:
            if c["score"] < min_score:
                continue
            if c["attr_id"] is None:
                # No podemos auto-aplicar: necesita una definición de atributo.
                # El usuario debe pasar por Claude Code para crearla con label legible.
                needs_claude.append({
                    "leaf": leaf, "field": c["field"], "kind_hint": c["kind_hint"],
                    "sample_values": c["sample_values"], "score": c["score"],
                })
                continue
            # Verificar que no esté ya
            existing = tax["leaf_filters"].setdefault(leaf, [])
            if any(f["id"] == c["attr_id"] for f in existing):
                continue
            existing.append({"id": c["attr_id"]})
            applied.append({
                "leaf": leaf, "attribute_id": c["attr_id"],
                "field": c["field"], "score": c["score"],
            })

    prompt = None
    if needs_claude:
        prompt = generate_claude_code_partial_prompt(needs_claude)

    return applied, prompt


def generate_claude_code_partial_prompt(items):
    """Prompt específico para los filtros que no se pudieron aplicar
    porque su atributo no está aún definido en attribute_definitions."""
    lines = [
        "# Tarea: definir atributos faltantes en taxonomy_editable.json",
        "",
        "El servidor Colsein detectó atributos discriminadores en la BD pero no están",
        "definidos en `attribute_definitions`. Necesito que los agregues con un label",
        "legible en español, y que los conectes a la hoja correspondiente.",
        "",
        "## Pasos:",
        "1. Edita `taxonomy_editable.json`",
        "2. Para cada item de abajo, agrega en `attribute_definitions` una entrada con un `attribute_id`",
        "   nuevo (en snake_case), un `label` legible, su `kind` y el `field` exacto",
        "3. Conecta el `attribute_id` a la hoja correspondiente en `leaf_filters`",
        "4. Después corre: `python3 colsein_agent_v3.py export-html colsein_app_v3.html`",
        "",
        "## Atributos a definir:",
        "",
    ]
    for it in items:
        lines.append(f"- Hoja: `{it['leaf']}`")
        lines.append(f"  - field: `{it['field']}` (kind sugerido: `{it['kind_hint']}`, score {it['score']})")
        lines.append(f"  - valores típicos: {', '.join(it['sample_values'][:5])}")
        lines.append(f"  - Crea attribute_id en snake_case con label legible. Ejemplo:")
        lines.append("    ```json")
        lines.append(f'    "<NUEVO_ID>": {{"label": "<Etiqueta humana>", "kind": "{it["kind_hint"]}", "field": "{it["field"]}"}}')
        lines.append("    ```")
        lines.append(f"  - Y en `leaf_filters[\"{it['leaf']}\"]` agrega: `{{\"id\": \"<NUEVO_ID>\"}}`")
        lines.append("")
    return "\n".join(lines)


def regen_html_from_template():
    """Regenera el HTML desde la BD usando el template estándar.
    Retorna la ruta del HTML generado."""
    template_path = DEFAULT_TEMPLATE
    if not template_path.exists():
        raise RuntimeError(f"No existe template: {template_path}")
    template = template_path.read_text(encoding="utf-8")

    conn = get_db()
    rows = conn.execute("SELECT * FROM products ORDER BY brand, leaf, model").fetchall()
    products = [row_to_compact(r) for r in rows]
    tax = load_taxonomy()

    from collections import defaultdict
    by_brand = defaultdict(list)
    for p in products:
        by_brand[p["brand"]].append(p)
    initial_ids = set()
    initial = []
    for bid in sorted(by_brand):
        for p in by_brand[bid][:2]:
            initial.append(p)
            initial_ids.add(p["id"])
    remaining = [p for p in products if p["id"] not in initial_ids]

    data = {
        "stats": {
            "total_products": len(products),
            "total_brands": len(tax["brands"]),
            "total_leaves": sum(1 for n in tax["nodes"] if n.get("is_leaf")),
            "initial_loaded": len(initial),
            "remaining_to_load": len(remaining),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "brands": tax["brands"],
        "taxonomy": tax["nodes"],
        "attribute_definitions": tax["attribute_definitions"],
        "leaf_filters": tax["leaf_filters"],
        "universal_filters": tax["universal_filters"],
        "products_initial": initial,
        "products_remaining": remaining,
    }
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("</script>", "<\\/script>")
    final = template.replace("__DATA_JSON__", data_json)
    out = GENERATED_HTML
    out.write_text(final, encoding="utf-8")
    log_operation(conn, "export", str(out.name), len(products))
    conn.commit()
    conn.close()
    return out


# ============================================================================
# Importador desde la API pública de colseinonline.com.co (WooCommerce REST)
# ============================================================================
COLSEIN_ONLINE_API = "https://colseinonline.com.co/wp-json/wc/store"
# Categorías top-level que NO son marcas (transversales)
COLSEIN_NON_BRAND_SLUGS = {"liquidacion", "promocion", "capacitaciones",
                            "filtros", "termostatos", "el-sol"}


def _strip_html(s):
    """Elimina etiquetas HTML y normaliza espacios."""
    import re
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _map_colsein_product(p, brand_cats_by_id, cats_map):
    """Mapea un producto de la API WC al schema interno de la BD.
    Retorna None si no se puede identificar la marca."""
    prod_cat_objs = p.get("categories", []) or []
    prod_cat_ids = [c.get("id") for c in prod_cat_objs if c.get("id") is not None]

    brand_cat = None
    sub_cats = []
    for cid in prod_cat_ids:
        if cid in brand_cats_by_id:
            # priorizar la marca con más productos si hay empate
            if brand_cat is None or brand_cats_by_id[cid].get("count", 0) > brand_cat.get("count", 0):
                brand_cat = brand_cats_by_id[cid]
        elif cid in cats_map:
            sub_cats.append(cats_map[cid])
    if not brand_cat:
        return None

    brand_slug = brand_cat["slug"]
    sub_cat = next((sc for sc in sub_cats if sc.get("parent") == brand_cat["id"]), None)
    if sub_cat:
        leaf_id = f"colsein-online.{brand_slug}.{sub_cat['slug']}"
        leaf_label = sub_cat["name"]
    else:
        leaf_id = f"colsein-online.{brand_slug}.general"
        leaf_label = "General"

    images = p.get("images") or []
    image_url = images[0].get("src") if images else None

    desc = _strip_html(p.get("short_description") or p.get("description") or "")
    if len(desc) > 500:
        desc = desc[:497] + "..."

    return {
        "id": f"colsein-online-{p['id']}",
        "brand": brand_slug,
        "model": (p.get("sku") or "").strip(),
        "name": p.get("name") or "(sin nombre)",
        "family": brand_cat.get("name"),
        "leaf": leaf_id,
        "leaf_label": leaf_label,
        "description": desc,
        "manufacturer_url": p.get("permalink"),
        "image_url": image_url,
        "attributes": {},
    }


def import_colsein_online(progress_cb=None):
    """Trae todos los productos de colseinonline.com.co vía WC API,
    auto-registra marcas/categorías nuevas en taxonomy_editable.json
    e inserta/actualiza productos en la BD.

    progress_cb(msg) opcional: callback para logging.

    Retorna dict con stats."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("Falta la dependencia 'requests'")

    log = (progress_cb or (lambda *a, **k: None))

    # 1. Categorías
    log(f"Trayendo categorías de {COLSEIN_ONLINE_API}/products/categories")
    cats_resp = requests.get(
        f"{COLSEIN_ONLINE_API}/products/categories",
        params={"per_page": 100}, timeout=30,
        headers={"User-Agent": SCRAPER_USER_AGENT})
    cats_resp.raise_for_status()
    cats_list = cats_resp.json()
    cats_map = {c["id"]: c for c in cats_list}
    brand_cats_by_id = {c["id"]: c for c in cats_list
                        if c.get("parent") == 0
                        and c.get("slug") not in COLSEIN_NON_BRAND_SLUGS
                        and c.get("count", 0) > 0}
    log(f"  {len(cats_list)} categorías totales, {len(brand_cats_by_id)} marcas detectadas")

    # 2. Cargar y preparar taxonomía
    tax = load_taxonomy()
    existing_brand_ids = {b["id"] for b in tax["brands"]}
    existing_node_ids = {n["id"] for n in tax["nodes"]}

    if "colsein-online" not in existing_node_ids:
        tax["nodes"].append({
            "id": "colsein-online",
            "label": "Colsein Online",
            "parent": "root",
            "is_leaf": False,
            "level": 1,
            "trunk": "colsein-online",
        })
        existing_node_ids.add("colsein-online")
        log("  + nodo trunk 'colsein-online'")

    new_brands = 0
    new_brand_nodes = 0
    for bcat in brand_cats_by_id.values():
        bslug = bcat["slug"]
        if bslug not in existing_brand_ids:
            tax["brands"].append({
                "id": bslug,
                "name": bcat.get("name") or bslug,
                "url": bcat.get("permalink") or "",
            })
            existing_brand_ids.add(bslug)
            new_brands += 1
        node_id = f"colsein-online.{bslug}"
        if node_id not in existing_node_ids:
            tax["nodes"].append({
                "id": node_id,
                "label": bcat.get("name") or bslug,
                "parent": "colsein-online",
                "is_leaf": False,
                "level": 2,
                "trunk": "colsein-online",
            })
            existing_node_ids.add(node_id)
            new_brand_nodes += 1
    log(f"  + {new_brands} marcas nuevas, {new_brand_nodes} nodos de marca nuevos")

    # 3. Paginar productos
    conn = get_db()
    inserted = updated = skipped_no_brand = 0
    by_brand_count = {}
    new_leaf_nodes = 0
    page = 1
    MAX_PAGES = 50  # safety
    while page <= MAX_PAGES:
        log(f"  GET productos página {page}")
        try:
            r = requests.get(
                f"{COLSEIN_ONLINE_API}/products",
                params={"per_page": 100, "page": page}, timeout=30,
                headers={"User-Agent": SCRAPER_USER_AGENT})
        except Exception as e:
            log(f"  error de red en página {page}: {e}")
            break
        if r.status_code == 400:
            # Past last page; WC retorna 400 en lugar de array vacío
            break
        if r.status_code != 200:
            log(f"  HTTP {r.status_code} en página {page}")
            break
        prods = r.json()
        if not prods:
            break
        log(f"    {len(prods)} productos recibidos")

        for p in prods:
            mapped = _map_colsein_product(p, brand_cats_by_id, cats_map)
            if not mapped:
                skipped_no_brand += 1
                continue
            leaf_id = mapped["leaf"]
            if leaf_id not in existing_node_ids:
                parent = ".".join(leaf_id.split(".")[:-1])
                if parent in existing_node_ids:
                    tax["nodes"].append({
                        "id": leaf_id,
                        "label": mapped["leaf_label"],
                        "parent": parent,
                        "is_leaf": True,
                        "level": 3,
                        "trunk": "colsein-online",
                    })
                    existing_node_ids.add(leaf_id)
                    new_leaf_nodes += 1
            row = conn.execute("SELECT id FROM products WHERE id = ?", (mapped["id"],)).fetchone()
            if row:
                conn.execute("""UPDATE products SET
                    brand=?, model=?, name=?, family=?, leaf=?, secondary_leaves=?,
                    description=?, manufacturer_url=?, image_url=?,
                    lifecycle=?, is_software=?, attributes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (mapped["brand"], mapped["model"], mapped["name"], mapped["family"],
                     mapped["leaf"], json.dumps([]), mapped["description"],
                     mapped["manufacturer_url"], mapped["image_url"],
                     "active", 0, json.dumps(mapped["attributes"]), mapped["id"]))
                updated += 1
            else:
                conn.execute("""INSERT INTO products
                    (id, brand, model, name, family, leaf, secondary_leaves,
                     description, manufacturer_url, image_url,
                     lifecycle, is_software, attributes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (mapped["id"], mapped["brand"], mapped["model"], mapped["name"],
                     mapped["family"], mapped["leaf"], json.dumps([]),
                     mapped["description"], mapped["manufacturer_url"], mapped["image_url"],
                     "active", 0, json.dumps(mapped["attributes"])))
                inserted += 1
            by_brand_count[mapped["brand"]] = by_brand_count.get(mapped["brand"], 0) + 1
        page += 1

    log_operation(conn, "import", "colsein-online-api", inserted + updated,
                  f"{inserted} nuevos, {updated} actualizados, {skipped_no_brand} sin marca")
    conn.commit()
    conn.close()

    # 4. Persistir taxonomía
    TAX_PATH.write_text(json.dumps(tax, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  taxonomía actualizada (+{new_leaf_nodes} hojas nuevas)")

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped_no_brand": skipped_no_brand,
        "by_brand": by_brand_count,
        "new_brands": new_brands,
        "new_leaf_nodes": new_leaf_nodes,
        "pages_fetched": page - 1,
    }


# ============================================================================
# Enriquecedor de atributos: extrae specs estructuradas del nombre/descripción
# de productos importados desde colseinonline.com.co (ID prefijo "colsein-online-").
# Sin LLM: regex puros sobre patrones del catálogo Colsein.
# ============================================================================

# Cada tupla: (attribute_id, regex pattern, transform fn or None, flags)
# El transform fn recibe el match group(1) (o el match completo si no hay grupo)
# y retorna el valor a guardar (str/int/float/None).
import re as _re

def _norm_lower(s):
    return s.strip().lower() if s else None

def _norm_int(s):
    try: return int(float(s))
    except: return None

def _norm_float(s):
    try:
        v = float(s)
        return int(v) if v == int(v) else round(v, 2)
    except: return None

# Patrones genéricos aplicables a casi cualquier producto. El orden importa
# (más específico primero). Si un pattern no matchea, simplemente se omite.
ENRICH_PATTERNS = [
    # ========== Sensores ==========
    ("tipo_sensor", r"\b(inductivo|capacitivo|fotoel[ée]ctrico|fotoelectrico|ultras[oó]nico|magn[eé]tico)\b", _norm_lower, _re.I),
    ("forma_sensor", r"\b(enrasado|no enrasado|no-enrasado|cuasi-enrasado|cilindrico|cil[íi]ndrico)\b", _norm_lower, _re.I),
    ("tamano_metric", r"\btama[ñn]o\s+(M\d{1,2})\b", lambda s: s.upper(), _re.I),
    ("tamano_metric_alt", r"\b(M\d{1,2})\s+(?:rango|rosca|cuerpo|cilindrico)", lambda s: s.upper(), _re.I),
    ("rango_mm", r"\brango\s+(\d+(?:[\.,]\d+)?)\s*mm\b", lambda s: _norm_float(s.replace(",", ".")), _re.I),
    ("salida_tipo", r"\bsalida\s+(PNP|NPN|push[-\s]?pull|push pull)\b", _norm_lower, _re.I),
    ("salida_estado", r"\bsalida\s+\w+\s+(NO|NC|N\.O\.|N\.C\.)\b", lambda s: s.upper().replace(".", ""), _re.I),
    ("conexion", r"\bconexi[óo]n\s+(M\d{1,2}|cable|terminal|bornera|cable\s+\d+\s*m)\b", _norm_lower, _re.I),
    ("ip_rating", r"\bIP\s*(\d{2}(?:\s*\/\s*\d+K?)?)", lambda s: "IP" + s.replace(" ", ""), _re.I),
    ("material_carcasa", r"\b(acero\s+inox(?:idable)?|niquelado|niquelada|lat[oó]n|pl[aá]stico|cromado|cromada)\b", _norm_lower, _re.I),
    ("io_link", r"\b(IO[-\s]?Link)\b", lambda s: True, _re.I),
    ("comunicacion_extra", r"\b(profinet|profibus|ethercat|ethernet|modbus|canopen|devicenet)\b", _norm_lower, _re.I),
    # ========== Eléctricos / motor / variador ==========
    ("voltaje_dc", r"\b(\d{1,3}(?:\s*-\s*\d{1,3})?)\s*V\s*DC\b", lambda s: s.replace(" ", ""), _re.I),
    ("voltaje_ac", r"\b(\d{2,3}(?:\s*-\s*\d{2,3})?)\s*V\s*AC\b", lambda s: s.replace(" ", ""), _re.I),
    ("voltaje", r"\b(24V|48V|110V|120V|208V|220V|230V|240V|277V|380V|400V|440V|480V|600V|690V)\b", lambda s: s.upper(), _re.I),
    ("fases", r"\b(monof[aá]sico|trif[aá]sico|bif[aá]sico|1\s*fase|3\s*fases?)\b", _norm_lower, _re.I),
    ("potencia_hp", r"\b(\d+(?:[\.,]\d+)?)\s*HP\b", lambda s: _norm_float(s.replace(",", ".")), _re.I),
    ("potencia_kw", r"\b(\d+(?:[\.,]\d+)?)\s*k\s*W\b", lambda s: _norm_float(s.replace(",", ".")), _re.I),
    ("rpm", r"\b(\d{3,5})\s*RPM\b", _norm_int, _re.I),
    ("frame_iec", r"\b(?:frame|carcasa|tama[ñn]o)\s+(\d{2,3}[A-Za-z]?)\b", lambda s: s.upper(), _re.I),
    ("polos_motor", r"\b(2|4|6|8)\s*polos\b", _norm_int, _re.I),
    # ========== Corriente / breakers / contactores ==========
    ("corriente_a", r"\b(\d{1,4}(?:[\.,]\d+)?)\s*A\b(?!.*HP)", lambda s: _norm_float(s.replace(",", ".")), _re.I),
    ("polos_interruptor", r"\b(\d)P\+?N?\b(?=.*polo)", _norm_int, _re.I),
    # ========== HMIs / PLCs ==========
    ("display_pulgadas", r"\b(\d+(?:[\.,]\d+)?)\s*(?:pulgadas|inch|\"|''|in)\b", lambda s: _norm_float(s.replace(",", ".")), _re.I),
    ("ethernet_ports", r"\b(\d+)\s*ethernet\b", _norm_int, _re.I),
    # ========== Cables ==========
    ("calibre_awg", r"\b(\d{1,2})\s*AWG\b", _norm_int, _re.I),
    ("conductores", r"\b(\d{1,2})\s*x\s*\d", _norm_int, _re.I),
    ("apantallado", r"\b(apantallado|blindado|shielded|sin\s+apantall)\b", _norm_lower, _re.I),
    # ========== Mecánicos (Item, Troax) ==========
    ("perfil_aluminio", r"\bperfil\s+(\d+x\d+)\b", lambda s: s.lower(), _re.I),
    ("altura_panel", r"\b(\d+)\s*mm\s+altura\b", _norm_int, _re.I),
]


def _extract_attributes(text):
    """Aplica todos los patrones a un string y retorna dict con los matches."""
    attrs = {}
    if not text:
        return attrs
    for entry in ENRICH_PATTERNS:
        if len(entry) == 4:
            attr_id, pattern, transform, flags = entry
        else:
            attr_id, pattern, transform = entry
            flags = 0
        # Si ya tenemos este atributo, omitir (el primer match gana)
        if attr_id in attrs:
            continue
        m = _re.search(pattern, text, flags)
        if not m:
            continue
        try:
            raw = m.group(1) if m.groups() else m.group(0)
        except IndexError:
            raw = m.group(0)
        val = transform(raw) if transform else raw
        if val is None:
            continue
        attrs[attr_id] = val
    return attrs


# Definiciones de atributos para taxonomy_editable.json. Auto-se registran
# las que sean usadas por al menos un producto.
ENRICH_ATTRIBUTE_DEFS = {
    "tipo_sensor":         {"label": "Tipo de sensor", "kind": "enum", "field": "tipo_sensor"},
    "forma_sensor":        {"label": "Forma", "kind": "enum", "field": "forma_sensor"},
    "tamano_metric":       {"label": "Tamaño rosca", "kind": "enum", "field": "tamano_metric"},
    "tamano_metric_alt":   {"label": "Tamaño cuerpo", "kind": "enum", "field": "tamano_metric_alt"},
    "rango_mm":            {"label": "Rango (mm)", "kind": "enum", "field": "rango_mm"},
    "salida_tipo":         {"label": "Tipo de salida", "kind": "enum", "field": "salida_tipo"},
    "salida_estado":       {"label": "Estado salida", "kind": "enum", "field": "salida_estado"},
    "conexion":            {"label": "Conexión", "kind": "enum", "field": "conexion"},
    "ip_rating":           {"label": "Grado IP", "kind": "enum", "field": "ip_rating"},
    "material_carcasa":    {"label": "Material carcasa", "kind": "enum", "field": "material_carcasa"},
    "io_link":             {"label": "IO-Link", "kind": "enum", "field": "io_link"},
    "comunicacion_extra":  {"label": "Comunicación", "kind": "enum", "field": "comunicacion_extra"},
    "voltaje_dc":          {"label": "Voltaje DC", "kind": "enum", "field": "voltaje_dc"},
    "voltaje_ac":          {"label": "Voltaje AC", "kind": "enum", "field": "voltaje_ac"},
    "voltaje":             {"label": "Voltaje", "kind": "enum", "field": "voltaje"},
    "fases":               {"label": "Fases", "kind": "enum", "field": "fases"},
    "potencia_hp":         {"label": "Potencia (HP)", "kind": "enum", "field": "potencia_hp"},
    "potencia_kw":         {"label": "Potencia (kW)", "kind": "enum", "field": "potencia_kw"},
    "rpm":                 {"label": "RPM", "kind": "enum", "field": "rpm"},
    "frame_iec":           {"label": "Frame", "kind": "enum", "field": "frame_iec"},
    "polos_motor":         {"label": "Polos motor", "kind": "enum", "field": "polos_motor"},
    "corriente_a":         {"label": "Corriente (A)", "kind": "enum", "field": "corriente_a"},
    "polos_interruptor":   {"label": "Polos interruptor", "kind": "enum", "field": "polos_interruptor"},
    "display_pulgadas":    {"label": "Display (\")", "kind": "enum", "field": "display_pulgadas"},
    "ethernet_ports":      {"label": "Puertos Ethernet", "kind": "enum", "field": "ethernet_ports"},
    "calibre_awg":         {"label": "Calibre AWG", "kind": "enum", "field": "calibre_awg"},
    "conductores":         {"label": "Conductores", "kind": "enum", "field": "conductores"},
    "apantallado":         {"label": "Apantallado", "kind": "enum", "field": "apantallado"},
    "perfil_aluminio":     {"label": "Perfil aluminio", "kind": "enum", "field": "perfil_aluminio"},
    "altura_panel":        {"label": "Altura panel (mm)", "kind": "enum", "field": "altura_panel"},
    # Atributos que vienen de import scrapeado (PLCs, HMIs)
    "display_size":        {"label": "Tamaño display", "kind": "enum", "field": "display_size"},
    "digital_inputs":      {"label": "Entradas digitales", "kind": "enum", "field": "digital_inputs"},
    "analog_inputs":       {"label": "Entradas analógicas", "kind": "enum", "field": "analog_inputs"},
    "transistor_outputs":  {"label": "Salidas transistor", "kind": "enum", "field": "transistor_outputs"},
    "relay_outputs":       {"label": "Salidas relay", "kind": "enum", "field": "relay_outputs"},
    "output_type":         {"label": "Tipo salida (PLC)", "kind": "enum", "field": "output_type"},
    "touch_type":          {"label": "Tipo touch", "kind": "enum", "field": "touch_type"},
    "resolution":          {"label": "Resolución", "kind": "enum", "field": "resolution"},
    "operating_temperature": {"label": "Temperatura operación", "kind": "enum", "field": "operating_temperature"},
    "clase_precision":     {"label": "Clase de precisión", "kind": "enum", "field": "clase_precision"},
}


def enrich_colsein_attributes(progress_cb=None):
    """Recorre productos importados desde colseinonline.com.co y aplica los
    patrones de extracción a (name + description). Suma los atributos
    extraídos a los existentes (sin pisar). Auto-registra attribute_definitions.

    Retorna stats dict."""
    log = (progress_cb or (lambda *a, **k: None))
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, description, attributes FROM products "
        "WHERE id LIKE 'colsein-online-%'"
    ).fetchall()
    log(f"Productos a enriquecer: {len(rows)}")

    used_attr_ids = set()
    products_updated = 0
    attr_added_total = 0
    attr_count_per_id = {}

    for row in rows:
        existing_attrs = json.loads(row["attributes"] or "{}")
        text = ((row["name"] or "") + " " + (row["description"] or "")).strip()
        new_attrs = _extract_attributes(text)
        if not new_attrs:
            continue
        # No pisar atributos existentes (preferimos lo manual)
        added_here = 0
        for k, v in new_attrs.items():
            if k not in existing_attrs:
                existing_attrs[k] = v
                used_attr_ids.add(k)
                attr_count_per_id[k] = attr_count_per_id.get(k, 0) + 1
                added_here += 1
        if added_here > 0:
            conn.execute("UPDATE products SET attributes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (json.dumps(existing_attrs), row["id"]))
            products_updated += 1
            attr_added_total += added_here

    # Adicionalmente, escanear TODOS los productos colsein-online-* y
    # juntar los IDs de atributos que ya tienen (no solo los que enrich agregó),
    # para registrar sus attribute_definitions también. Esto cubre productos
    # importados con atributos pre-llenados (como los scrapeados de Unitronics).
    all_used_attr_ids = set(used_attr_ids)
    rows_full = conn.execute(
        "SELECT attributes FROM products WHERE id LIKE 'colsein-online-%' OR id LIKE 'scraped-%'"
    ).fetchall()
    for row in rows_full:
        attrs = json.loads(row["attributes"] or "{}")
        for k in attrs.keys():
            all_used_attr_ids.add(k)

    log_operation(conn, "update", "enrich-colsein", products_updated,
                  f"+{attr_added_total} atributos en {products_updated} productos")
    conn.commit()
    conn.close()

    # Registrar attribute_definitions usadas
    tax = load_taxonomy()
    if "attribute_definitions" not in tax:
        tax["attribute_definitions"] = {}
    new_defs = 0
    for aid in all_used_attr_ids:
        if aid not in tax["attribute_definitions"] and aid in ENRICH_ATTRIBUTE_DEFS:
            tax["attribute_definitions"][aid] = ENRICH_ATTRIBUTE_DEFS[aid]
            new_defs += 1
    TAX_PATH.write_text(json.dumps(tax, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  +{new_defs} attribute_definitions registradas")

    return {
        "products_scanned": len(rows),
        "products_updated": products_updated,
        "attributes_added_total": attr_added_total,
        "attributes_used_count_per_id": attr_count_per_id,
        "new_attribute_definitions": new_defs,
    }


# ============================================================================
# Construcción de la app Flask (compartida por `serve` y wsgi.py / gunicorn)
# ============================================================================
def build_app():
    """Construye la app Flask con todas las rutas y la retorna.

    Se usa tanto desde `cmd_serve` (Flask dev server) como desde wsgi.py
    (gunicorn en producción/Railway).
    """
    try:
        from flask import Flask, jsonify, request, send_from_directory
    except ImportError:
        die("Instala Flask: pip install flask")

    app = Flask(__name__)

    @app.route("/")
    def home():
        # Busca cualquier HTML conocido (por orden de preferencia)
        for name in ["colsein_app_v3.html", "colsein_app.html"]:
            html_path = DATA_DIR / name
            if html_path.exists():
                return html_path.read_text(encoding="utf-8")
        return ("<h1>Frontend no encontrado</h1>"
                "<p>No existe colsein_app_v3.html ni colsein_app.html en " + str(DATA_DIR) + "</p>"
                "<p>Genéralo con: <code>python3 colsein_agent_v3.py export-html colsein_app_v3.html</code></p>")

    @app.route("/api/products")
    def api_products():
        conn = get_db()
        rows = conn.execute("SELECT * FROM products").fetchall()
        out = [dict(r) for r in rows]
        for o in out:
            o["attributes"] = json.loads(o["attributes"] or "{}")
            o["secondary_leaves"] = json.loads(o["secondary_leaves"] or "[]")
        conn.close()
        return jsonify(out)

    @app.route("/api/taxonomy")
    def api_taxonomy():
        return jsonify(load_taxonomy())

    @app.route("/api/products/<product_id>/image")
    def api_product_image(product_id):
        """Sirve el blob local de la imagen del producto."""
        conn = get_db()
        row = conn.execute(
            "SELECT image_blob, image_mime FROM products WHERE id = ?",
            (product_id,)).fetchone()
        conn.close()
        if not row or row["image_blob"] is None:
            return "Imagen no disponible", 404
        from flask import Response
        return Response(row["image_blob"], mimetype=row["image_mime"] or "image/jpeg")

    @app.route("/api/products", methods=["POST"])
    def api_create_product():
        data = request.json
        p = normalize_product(data)
        if not p:
            return jsonify({"error": "formato inválido"}), 400
        conn = get_db()
        try:
            conn.execute("""INSERT INTO products
                (id, brand, model, name, family, leaf, secondary_leaves,
                 description, manufacturer_url, datasheet_url, image_url,
                 lifecycle, is_software, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["id"], p["brand"], p["model"], p["name"], p["family"],
                 p["leaf"], json.dumps(p["secondary_leaves"]), p["description"],
                 p["manufacturer_url"], p["datasheet_url"], p.get("image_url"),
                 p["lifecycle"], p["is_software"], json.dumps(p["attributes"])))
            conn.commit()
            conn.close()
            return jsonify({"ok": True, "id": p["id"]})
        except sqlite3.IntegrityError as e:
            conn.close()
            return jsonify({"error": str(e)}), 409

    # ========================================================================
    # ENDPOINTS ADMIN
    # ========================================================================
    # Nota: la autenticación es básica (cookie de sesión). NO es seguridad real,
    # solo separa interfaces. Para seguridad real usar auth + HTTPS + secret real.
    # Lee env var: si está ausente o vacía/whitespace, retorna el default.
    # (Importante: os.environ.get(k, default) NO usa default si la var existe
    # con valor vacío — y Railway/Heroku permiten guardar variables vacías.)
    def _env(name, default):
        val = (os.environ.get(name) or "").strip()
        return val if val else default

    ADMIN_USER = _env("ADMIN_USER", "Felipe")
    ADMIN_PASS = _env("ADMIN_PASS", "Felipe")
    import secrets as _sec
    import hmac as _hmac
    import hashlib as _hashlib
    import base64 as _base64
    app.secret_key = _env("FLASK_SECRET_KEY", _sec.token_hex(32))
    _SIGN_KEY = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    if ADMIN_PASS == "Felipe":
        warn("ADMIN_PASS no configurado o vacío: usando contraseña por defecto 'Felipe'. "
             "En producción exporta ADMIN_USER y ADMIN_PASS como variables de entorno.")

    def _sign_token(payload_str):
        """Tokens stateless firmados HMAC. Cualquier worker los valida sin
        necesidad de un store compartido. Formato: {payload}.{signature}"""
        sig = _hmac.new(_SIGN_KEY, payload_str.encode(), _hashlib.sha256).digest()
        sig_b64 = _base64.urlsafe_b64encode(sig).decode().rstrip("=")
        return f"{payload_str}.{sig_b64}"

    def _verify_token(token):
        if not token or "." not in token:
            return False
        payload_str, sig_b64 = token.rsplit(".", 1)
        expected = _hmac.new(_SIGN_KEY, payload_str.encode(), _hashlib.sha256).digest()
        provided = _base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not _hmac.compare_digest(expected, provided):
            return False
        # payload_str = "<user>:<issued_at>". Validar TTL (24h).
        try:
            user, issued = payload_str.split(":", 1)
            issued_at = int(issued)
        except Exception:
            return False
        import time as _t
        if _t.time() - issued_at > 86400:
            return False
        return True

    def require_admin():
        from flask import request as flreq
        token = flreq.headers.get("X-Admin-Token") or flreq.cookies.get("colsein_admin")
        return _verify_token(token)

    @app.route("/api/health")
    def api_health():
        """Permite al frontend detectar si el servidor está corriendo."""
        return jsonify({"ok": True, "version": 4, "service": "colsein-agent"})

    @app.route("/api/admin/login", methods=["POST"])
    def api_admin_login():
        data = request.json or {}
        user_in = (data.get("user") or "").strip().lower()
        pass_in = data.get("password") or ""
        if user_in == ADMIN_USER.lower() and pass_in == ADMIN_PASS:
            import time as _t
            payload = f"{user_in}:{int(_t.time())}"
            tok = _sign_token(payload)
            return jsonify({"ok": True, "token": tok})
        return jsonify({"ok": False, "error": "Credenciales inválidas"}), 401

    @app.route("/api/admin/logout", methods=["POST"])
    def api_admin_logout():
        # Tokens stateless: el cliente debe descartar su token. No hay store que limpiar.
        return jsonify({"ok": True})

    @app.route("/api/admin/stats")
    def api_admin_stats():
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        conn = get_db()
        n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        n_img = conn.execute("SELECT COUNT(*) FROM products WHERE image_url IS NOT NULL").fetchone()[0]
        n_blob = conn.execute("SELECT COUNT(*) FROM products WHERE image_blob IS NOT NULL").fetchone()[0]
        by_brand = conn.execute(
            "SELECT brand, COUNT(*) as n FROM products GROUP BY brand ORDER BY n DESC"
        ).fetchall()
        recent = conn.execute(
            "SELECT operation, target, items, timestamp FROM load_log ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return jsonify({
            "total_products": n,
            "products_with_image_url": n_img,
            "products_with_local_blob": n_blob,
            "by_brand": [dict(r) for r in by_brand],
            "recent_operations": [dict(r) for r in recent],
        })

    @app.route("/api/admin/find-products", methods=["POST"])
    def api_admin_find_products():
        """Busca productos NUEVOS (los que aún no están en la BD).

        Si el body trae {"brand": "sick"}: solo esa marca.
        Si no: todas las marcas, distribuyendo el batch.
        Target mínimo: 200 productos (o lo que se pueda).
        """
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401

        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return jsonify({"error": "Faltan dependencias del servidor: pip install requests beautifulsoup4 lxml"}), 500

        data = request.json or {}
        target_brand = data.get("brand")
        target_count = int(data.get("target", 200))

        tax = load_taxonomy()
        if target_brand:
            brands_list = [b for b in tax["brands"] if b["id"] == target_brand]
            if not brands_list:
                return jsonify({"error": f"Marca no reconocida: {target_brand}"}), 400
        else:
            brands_list = list(tax["brands"])

        conn = get_db()
        existing_urls = set(r["manufacturer_url"] for r in
            conn.execute("SELECT manufacturer_url FROM products WHERE manufacturer_url IS NOT NULL").fetchall())
        existing_ids = set(r["id"] for r in conn.execute("SELECT id FROM products").fetchall())

        session = requests.Session()
        session.headers["User-Agent"] = SCRAPER_USER_AGENT

        # Distribuir batch entre marcas si es general
        per_brand = max(10, target_count // len(brands_list))
        log_lines = []
        total_new = 0
        scanned = 0

        for brand_info in brands_list:
            if total_new >= target_count:
                break
            bid = brand_info["id"]
            base_url = brand_info.get("url")
            if not base_url:
                log_lines.append(f"[{bid}] sin URL configurada, omitiendo")
                continue
            log_lines.append(f"[{bid}] GET {base_url}")
            try:
                time.sleep(SCRAPER_RATE_LIMIT)
                r = session.get(base_url, timeout=20)
                if r.status_code != 200:
                    log_lines.append(f"[{bid}] HTTP {r.status_code}, omitiendo")
                    continue
            except Exception as e:
                log_lines.append(f"[{bid}] error: {e}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            candidate_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(k in href.lower() for k in ["/product", "/products/", "/p/", "/catalog"]):
                    if href.startswith("/"):
                        href = base_url.rstrip("/") + href
                    elif not href.startswith("http"):
                        continue
                    if href in existing_urls:
                        continue
                    candidate_links.append((href, a.get_text(strip=True)[:80]))

            candidate_links = list(dict.fromkeys(candidate_links))[:per_brand]
            scanned += len(candidate_links)
            log_lines.append(f"[{bid}] {len(candidate_links)} productos nuevos candidatos")

            inserted_brand = 0
            for url, label in candidate_links:
                if total_new >= target_count:
                    break
                pid = f"{bid}-scraped-{abs(hash(url)) & 0xFFFFFF:06x}"
                if pid in existing_ids:
                    continue
                title = label or url.rstrip("/").split("/")[-1].replace("-", " ").title() or "Sin título"
                try:
                    conn.execute("""INSERT INTO products
                        (id, brand, model, name, leaf, description, manufacturer_url,
                         lifecycle, is_software, attributes, secondary_leaves)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, '{}', '[]')""",
                        (pid, bid, "", title[:200], "needs_classification",
                         (label or "")[:500], url))
                    existing_ids.add(pid)
                    existing_urls.add(url)
                    inserted_brand += 1
                    total_new += 1
                except sqlite3.IntegrityError:
                    pass
            log_lines.append(f"[{bid}] +{inserted_brand} insertados (total acumulado: {total_new})")

        log_operation(conn, "scrape", target_brand or "*all*", total_new,
                      f"escaneados {scanned}, insertados {total_new}")
        conn.commit()
        conn.close()

        return jsonify({
            "ok": True,
            "scanned": scanned,
            "inserted": total_new,
            "target": target_count,
            "log": log_lines,
            "next_step": "Los productos nuevos quedaron en leaf='needs_classification'. " \
                         "Usa Claude AI para clasificarlos: export-json sin_clasificar.json " \
                         "→ Claude AI los clasifica → import-json clasificado.json --replace",
        })

    @app.route("/api/admin/refresh-filters", methods=["POST"])
    def api_admin_refresh_filters():
        """Analiza la BD y retorna sugerencias de filtros.

        Si auto_apply=true: aplica las sugerencias con score > 0.6 directamente
        al taxonomy_editable.json.
        """
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401

        data = request.json or {}
        auto_apply = data.get("auto_apply", False)
        min_score = float(data.get("min_score", 0.6))
        min_products = int(data.get("min_products", 5))

        tax = load_taxonomy()
        suggestions = compute_filter_suggestions(tax, min_products=min_products)

        applied = []
        prompt_for_claude = None
        if auto_apply and suggestions:
            applied, prompt_for_claude = apply_filter_suggestions(tax, suggestions, min_score)
            if applied:
                # Guardar taxonomy actualizada
                TAX_PATH.write_text(json.dumps(tax, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                # Regenerar HTML automáticamente
                try:
                    regen_html_from_template()
                    html_regenerated = True
                except Exception as e:
                    html_regenerated = False

        return jsonify({
            "ok": True,
            "suggestions": suggestions,
            "applied": applied,
            "auto_applied": bool(applied),
            "prompt_for_claude_code": prompt_for_claude,
            "html_regenerated": auto_apply and bool(applied),
        })

    @app.route("/api/admin/regenerate-html", methods=["POST"])
    def api_admin_regenerate():
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        try:
            out = regen_html_from_template()
            return jsonify({"ok": True, "html_path": str(out), "size_kb": round(os.path.getsize(out)/1024, 1)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/admin/register-filters", methods=["POST"])
    def api_admin_register_filters():
        """Registra attribute_definitions, leaf_filters, y opcionalmente nodes
        nuevos de taxonomia. Body: {
          "definitions": {"<attr_id>": {"label": "...", "kind": "enum|enum_multi", "field": "..."}, ...},
          "leaf_filters": {"<leaf_id>": ["<attr_id>", ...], ...},
          "nodes": [{"id": "...", "label": "...", "parent": "...", "is_leaf": bool}, ...]
        }"""
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        body = request.json or {}
        tax = load_taxonomy()
        if "attribute_definitions" not in tax:
            tax["attribute_definitions"] = {}
        if "leaf_filters" not in tax:
            tax["leaf_filters"] = {}
        if "nodes" not in tax:
            tax["nodes"] = []

        # 0) Nodos nuevos (antes de leaf_filters, por si los nuevos filtros
        #    referencian leaves recien creadas)
        existing_node_ids = {n["id"] for n in tax["nodes"]}
        added_nodes = 0
        for n in body.get("nodes") or []:
            nid = n.get("id")
            if not nid or nid in existing_node_ids:
                continue
            parent = n.get("parent") or "root"
            # Calcular level desde el path del id (a.b.c -> level 3)
            level = nid.count(".") + 1 if nid != "root" else 0
            trunk = nid.split(".")[0] if "." in nid else nid
            tax["nodes"].append({
                "id": nid,
                "label": n.get("label") or nid.split(".")[-1].replace("-", " ").title(),
                "parent": parent,
                "is_leaf": bool(n.get("is_leaf", True)),
                "level": level,
                "trunk": n.get("trunk") or trunk,
            })
            existing_node_ids.add(nid)
            added_nodes += 1

        added_defs = 0
        skipped_defs = 0
        for aid, info in (body.get("definitions") or {}).items():
            if not isinstance(info, dict) or "field" not in info:
                continue
            if aid in tax["attribute_definitions"]:
                skipped_defs += 1
                continue
            tax["attribute_definitions"][aid] = {
                "label": info.get("label") or aid,
                "kind": info.get("kind") or "enum",
                "field": info["field"],
            }
            added_defs += 1

        added_filters = 0
        unknown_attrs = []
        for leaf, aids in (body.get("leaf_filters") or {}).items():
            if leaf not in tax["leaf_filters"]:
                tax["leaf_filters"][leaf] = []
            existing = {f.get("id") for f in tax["leaf_filters"][leaf] if isinstance(f, dict)}
            for aid in (aids or []):
                if aid not in tax["attribute_definitions"]:
                    unknown_attrs.append({"leaf": leaf, "attr": aid})
                    continue
                if aid in existing:
                    continue
                tax["leaf_filters"][leaf].append({"id": aid})
                existing.add(aid)
                added_filters += 1

        TAX_PATH.write_text(json.dumps(tax, ensure_ascii=False, indent=2), encoding="utf-8")

        html_ok = False
        try:
            regen_html_from_template()
            html_ok = True
        except Exception as e:
            pass

        return jsonify({
            "ok": True,
            "added_nodes": added_nodes,
            "added_definitions": added_defs,
            "skipped_definitions_already_present": skipped_defs,
            "added_filters": added_filters,
            "unknown_attrs": unknown_attrs,
            "html_regenerated": html_ok,
        })

    @app.route("/api/admin/upload-images-batch", methods=["POST"])
    def api_admin_upload_images_batch():
        """Sube imagenes (binarias en base64) y las asocia a productos.
        Body: {"images": [{"product_ids": [...], "data_b64": "...", "mime": "image/jpeg"}, ...]}
        Cada imagen se decodifica una vez y se asocia a todos sus product_ids."""
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        import base64 as _b64
        body = request.json or {}
        items = body.get("images") or []
        if not isinstance(items, list):
            return jsonify({"error": "images debe ser array"}), 400
        conn = get_db()
        updated = 0
        skipped = 0
        for it in items:
            ids = it.get("product_ids") or []
            data_b64 = it.get("data_b64") or ""
            mime = it.get("mime") or "image/jpeg"
            if not ids or not data_b64:
                continue
            try:
                blob = _b64.b64decode(data_b64)
            except Exception:
                skipped += len(ids)
                continue
            for pid in ids:
                row = conn.execute("SELECT id FROM products WHERE id = ?", (pid,)).fetchone()
                if not row:
                    skipped += 1
                    continue
                conn.execute(
                    "UPDATE products SET image_blob=?, image_mime=?, "
                    "image_status='blob_only', image_checked_at=CURRENT_TIMESTAMP, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (blob, mime, pid))
                updated += 1
        log_operation(conn, "images", "upload-batch", updated)
        conn.commit()
        conn.close()
        # Regenerar HTML para que el frontend incluya las nuevas referencias
        html_ok = False
        try:
            regen_html_from_template()
            html_ok = True
        except Exception:
            pass
        return jsonify({
            "ok": True,
            "updated": updated,
            "skipped": skipped,
            "html_regenerated": html_ok,
        })

    @app.route("/api/admin/import-products-batch", methods=["POST"])
    def api_admin_import_products_batch():
        """Inserta o actualiza un batch de productos enviados en JSON.
        Espera body: {"products": [{...}, ...]} con cada producto en formato
        normalize_product. Usa upsert por id."""
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        body = request.json or {}
        products_in = body.get("products") or []
        if not isinstance(products_in, list):
            return jsonify({"error": "products debe ser array"}), 400

        conn = get_db()
        inserted = updated = skipped = 0
        errors = []
        for raw in products_in:
            p = normalize_product(raw)
            if not p:
                skipped += 1
                continue
            try:
                row = conn.execute("SELECT id FROM products WHERE id = ?", (p["id"],)).fetchone()
                if row:
                    conn.execute("""UPDATE products SET
                        brand=?, model=?, name=?, family=?, leaf=?, secondary_leaves=?,
                        description=?, manufacturer_url=?, datasheet_url=?, image_url=?,
                        lifecycle=?, is_software=?, attributes=?, updated_at=CURRENT_TIMESTAMP
                        WHERE id=?""",
                        (p["brand"], p["model"], p["name"], p["family"], p["leaf"],
                         json.dumps(p["secondary_leaves"]), p["description"],
                         p["manufacturer_url"], p["datasheet_url"], p.get("image_url"),
                         p["lifecycle"], p["is_software"], json.dumps(p["attributes"]),
                         p["id"]))
                    updated += 1
                else:
                    conn.execute("""INSERT INTO products
                        (id, brand, model, name, family, leaf, secondary_leaves,
                         description, manufacturer_url, datasheet_url, image_url,
                         lifecycle, is_software, attributes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (p["id"], p["brand"], p["model"], p["name"], p["family"], p["leaf"],
                         json.dumps(p["secondary_leaves"]), p["description"],
                         p["manufacturer_url"], p["datasheet_url"], p.get("image_url"),
                         p["lifecycle"], p["is_software"], json.dumps(p["attributes"])))
                    inserted += 1
            except Exception as e:
                errors.append({"id": p.get("id"), "error": str(e)})
        log_operation(conn, "import", "scraped-batch", inserted + updated,
                      f"{inserted} nuevos, {updated} actualizados, {skipped} omitidos")
        conn.commit()
        conn.close()
        # Regenerar HTML
        html_ok = False
        try:
            regen_html_from_template()
            html_ok = True
        except Exception as e:
            errors.append({"html_regen": str(e)})
        return jsonify({
            "ok": True,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "html_regenerated": html_ok,
        })

    @app.route("/api/admin/enrich-attributes", methods=["POST"])
    def api_admin_enrich_attributes():
        """Aplica el extractor de atributos por regex a todos los productos
        de colseinonline.com.co existentes. No usa LLM. Idempotente."""
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        log_lines = []
        try:
            stats = enrich_colsein_attributes(progress_cb=log_lines.append)
        except Exception as e:
            return jsonify({"error": str(e), "log": log_lines}), 500
        # Regenerar HTML para que el frontend vea los nuevos atributos
        try:
            regen_html_from_template()
            html_ok = True
        except Exception as e:
            log_lines.append(f"⚠ Error regenerando HTML: {e}")
            html_ok = False
        return jsonify({
            "ok": True,
            "stats": stats,
            "html_regenerated": html_ok,
            "log": log_lines,
            "next_step": "Click en 'Actualizar filtros' con auto-aplicar marcado "
                         "para que los nuevos atributos se conviertan en filtros progresivos.",
        })

    @app.route("/api/admin/import-colsein-online", methods=["POST"])
    def api_admin_import_colsein():
        """Importa todos los productos de colseinonline.com.co vía la API
        pública de WooCommerce, auto-registrando marcas/categorías y
        regenerando el HTML al final."""
        if not require_admin():
            return jsonify({"error": "no autorizado"}), 401
        log_lines = []
        try:
            stats = import_colsein_online(progress_cb=log_lines.append)
        except Exception as e:
            return jsonify({"error": str(e), "log": log_lines}), 500

        html_ok = False
        try:
            regen_html_from_template()
            html_ok = True
            log_lines.append("HTML regenerado")
        except Exception as e:
            log_lines.append(f"⚠ Error al regenerar HTML: {e}")

        return jsonify({
            "ok": True,
            "stats": stats,
            "html_regenerated": html_ok,
            "log": log_lines,
            "next_step": "Recarga la página con Ctrl+F5 para ver los productos. "
                         "Después click en 'Actualizar filtros' para generar filtros "
                         "automáticos basados en las nuevas categorías.",
        })

    info(f"Endpoints admin disponibles bajo /api/admin/* (login: {ADMIN_USER}/***)")

    return app


# ============================================================================
# Comando: serve (wrapper que lanza la app construida en build_app)
# ============================================================================
def cmd_serve(args):
    """Servidor Flask local. En producción se usa gunicorn vía wsgi.py."""
    app = build_app()
    port = int(os.environ.get("PORT", args.port))
    # Si PORT viene del entorno (Railway/Heroku), bind a 0.0.0.0; si no, localhost.
    host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    info(f"Servidor en http://{host}:{port}")
    info(f"  GET  /                              HTML del catálogo")
    info(f"  GET  /api/health                    Healthcheck (detecta servidor desde frontend)")
    info(f"  GET  /api/products                  Lista de productos JSON")
    info(f"  GET  /api/products/<id>/image       Imagen local del producto (blob)")
    info(f"  GET  /api/taxonomy                  Taxonomía y filtros")
    info(f"  POST /api/products                  Agregar producto (JSON body)")
    info(f"  POST /api/admin/login               Login admin")
    info(f"  POST /api/admin/find-products       Buscar productos nuevos por marca o general")
    info(f"  POST /api/admin/refresh-filters     Analiza BD y propone/aplica filtros nuevos")
    info(f"  POST /api/admin/regenerate-html     Regenera el HTML")
    app.run(host=host, port=port, debug=False)


# ============================================================================
# CLI
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Colsein Agent v3 - Backend SQLite para catálogo de productos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Crea/migra la base de datos")

    pi = sub.add_parser("import-json", help="Importa productos desde JSON")
    pi.add_argument("archivo")
    pi.add_argument("--replace", action="store_true",
                    help="Reemplaza productos existentes")

    pe = sub.add_parser("export-json", help="Exporta BD a JSON")
    pe.add_argument("archivo")

    ph = sub.add_parser("export-html", help="Genera HTML autosuficiente con dataset embebido")
    ph.add_argument("archivo")
    ph.add_argument("--template", help=f"Template HTML (default: {DEFAULT_TEMPLATE.name})")

    sub.add_parser("add-product", help="Agrega 1 producto interactivamente")

    pl = sub.add_parser("add-leaf", help="Agrega una hoja de taxonomía")
    pl.add_argument("leaf_id", help="ID jerárquico, ej: deteccion-posicionamiento.nueva-hoja")
    pl.add_argument("label", help="Etiqueta legible")

    pf = sub.add_parser("add-filter", help="Agrega un filtro progresivo a una hoja")
    pf.add_argument("leaf_id")
    pf.add_argument("attribute_id")

    pdi = sub.add_parser("download-images", help="Descarga imágenes de productos como blob local (respaldo)")
    pdi.add_argument("--brand", help="Filtrar por una sola marca")
    pdi.add_argument("--limit", type=int, help="Máximo de imágenes a descargar")
    pdi.add_argument("--recheck", action="store_true", help="Reintenta también las URLs marcadas como rotas")

    psi = sub.add_parser("set-image", help="Asigna una imagen a un producto (URL o archivo local)")
    psi.add_argument("product_id")
    psi.add_argument("--url", help="URL de la imagen")
    psi.add_argument("--file", help="Archivo local (jpg/png/webp)")

    psf = sub.add_parser("suggest-filters", help="Analiza la BD y sugiere filtros progresivos nuevos")
    psf.add_argument("--min-products", type=int, default=5,
                     help="Mínimo de productos por hoja para considerarla (default 5)")
    psf.add_argument("--top", type=int, default=5,
                     help="Top N atributos por hoja (default 5)")
    psf.add_argument("--max-leaves", type=int, default=30,
                     help="Máximo hojas a mostrar (default 30)")
    psf.add_argument("--output", help="Guardar sugerencias como prompt para Claude Code")

    sub.add_parser("stats", help="Estadísticas de la BD")
    sub.add_parser("refine", help="Limpia y valida la BD")

    ps = sub.add_parser("scrape", help="Scraping real (placeholder, requiere ajustes por marca)")
    ps.add_argument("--brand", required=True)
    ps.add_argument("--batch", type=int, default=50)

    pv = sub.add_parser("serve", help="Servidor Flask local (opcional)")
    pv.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    handlers = {
        "init": cmd_init,
        "import-json": cmd_import_json,
        "export-json": cmd_export_json,
        "export-html": cmd_export_html,
        "add-product": cmd_add_product,
        "add-leaf": cmd_add_leaf,
        "add-filter": cmd_add_filter,
        "download-images": cmd_download_images,
        "set-image": cmd_set_image,
        "suggest-filters": cmd_suggest_filters,
        "stats": cmd_stats,
        "refine": cmd_refine,
        "scrape": cmd_scrape,
        "serve": cmd_serve,
    }
    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
