"""Reasigna los productos de las trunks 'phoenix-contact' y 'colsein-online'
a hojas SEO reales y luego borra ambos arboles de la taxonomia.

Pasos:
  1. GET /api/products: descarga el dataset.
  2. Para cada producto en phoenix-contact.* o colsein-online.*: calcula la
     nueva hoja segun mapeos (prefijo de modelo + brand + sub-categoria).
  3. POST /api/admin/import-products-batch en chunks de 500.
  4. POST /api/admin/delete-nodes con las dos trunks para limpiar la
     taxonomia y los leaf_filters asociados.

Requiere variables de entorno:
  COLSEIN_URL    (default https://web-production-f7337.up.railway.app)
  ADMIN_USER     (obligatoria)
  ADMIN_PASS     (obligatoria)

Uso:
  python redistribute_phoenix_colsein.py [--dry-run]
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict


BASE_URL = os.environ.get("COLSEIN_URL", "https://web-production-f7337.up.railway.app").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER")
ADMIN_PASS = os.environ.get("ADMIN_PASS")


# ---------------------------------------------------------------------------
# Mapeo phoenix-contact.catalogo-general por prefijo de modelo
# ---------------------------------------------------------------------------
# Orden importa: prefijos largos primero (greedy match).
PHOENIX_PREFIX_MAP = [
    # Conectores PCB (pluggable)
    ("DFK-MSTB", "conectores-industriales.conectores-pcb"),
    ("DFK-PC",   "conectores-industriales.conectores-pcb"),
    ("DFK",      "conectores-industriales.conectores-pcb"),
    ("DFMC",     "conectores-industriales.conectores-pcb"),
    ("FKIC",     "conectores-industriales.conectores-pcb"),
    ("FKCT",     "conectores-industriales.conectores-pcb"),
    ("FKCS",     "conectores-industriales.conectores-pcb"),
    ("FKCN",     "conectores-industriales.conectores-pcb"),
    ("FKCV",     "conectores-industriales.conectores-pcb"),
    ("FKC",      "conectores-industriales.conectores-pcb"),
    ("FK-MC",    "conectores-industriales.conectores-pcb"),
    ("FK-MCP",   "conectores-industriales.conectores-pcb"),
    ("FK",       "conectores-industriales.conectores-pcb"),
    ("GICV",     "conectores-industriales.conectores-pcb"),
    ("GIC",      "conectores-industriales.conectores-pcb"),
    ("GFKC",     "conectores-industriales.conectores-pcb"),
    ("GFKIC",    "conectores-industriales.conectores-pcb"),
    ("GMVSTBR",  "conectores-industriales.conectores-pcb"),
    ("GMVSTBW",  "conectores-industriales.conectores-pcb"),
    ("ICC",      "conectores-industriales.conectores-pcb"),
    ("IDC",      "conectores-industriales.conectores-pcb"),
    ("IFMC",     "conectores-industriales.conectores-pcb"),
    ("IMC",      "conectores-industriales.conectores-pcb"),
    ("ISPC",     "conectores-industriales.conectores-pcb"),
    ("MSTBV",    "conectores-industriales.conectores-pcb"),
    ("PTSM",     "conectores-industriales.conectores-pcb"),
    ("QC",       "conectores-industriales.conectores-pcb"),
    ("TFKC",     "conectores-industriales.conectores-pcb"),
    ("TFMC",     "conectores-industriales.conectores-pcb"),
    ("TMSTBP",   "conectores-industriales.conectores-pcb"),
    ("TPC",      "conectores-industriales.conectores-pcb"),
    ("TSPC",     "conectores-industriales.conectores-pcb"),
    ("TVFKCL",   "conectores-industriales.conectores-pcb"),
    ("TVFKC",    "conectores-industriales.conectores-pcb"),
    ("TVMSTB",   "conectores-industriales.conectores-pcb"),
    ("XPC",      "conectores-industriales.conectores-pcb"),
    ("ZEC",      "conectores-industriales.conectores-pcb"),

    # Borneras PCB vertical / angular
    ("MDSTBV",   "borneras-y-conexion.borneras-pcb-vertical"),
    ("MDSTB",    "borneras-y-conexion.borneras-pcb"),
    ("GMSTBVA",  "borneras-y-conexion.borneras-pcb-vertical"),
    ("GMSTBV",   "borneras-y-conexion.borneras-pcb-vertical"),
    ("GMSTBA",   "borneras-y-conexion.borneras-pcb-vertical"),
    ("UMSTBVK",  "borneras-y-conexion.borneras-pcb-vertical"),

    # Borneras alta corriente / power
    ("DD32H",    "borneras-y-conexion.borneras-alta-corriente"),
    ("DD31H",    "borneras-y-conexion.borneras-alta-corriente"),
    ("DD21H",    "borneras-y-conexion.borneras-alta-corriente"),
    ("DD32PC",   "borneras-y-conexion.borneras-alta-corriente"),
    ("DD31PC",   "borneras-y-conexion.borneras-alta-corriente"),
    ("DD21PC",   "borneras-y-conexion.borneras-alta-corriente"),
    ("DD31PS",   "borneras-y-conexion.borneras-alta-corriente"),
    ("D32H",     "borneras-y-conexion.borneras-alta-corriente"),
    ("D31H",     "borneras-y-conexion.borneras-alta-corriente"),
    ("D32PC",    "borneras-y-conexion.borneras-alta-corriente"),
    ("D31PC",    "borneras-y-conexion.borneras-alta-corriente"),

    # Borneras DIN (tornillo / push-in / spring)
    ("UWV",      "borneras-y-conexion.borneras-tornillo"),
    ("UW",       "borneras-y-conexion.borneras-tornillo"),
    ("USLKG",    "borneras-y-conexion.borneras-tornillo"),
    ("UK",       "borneras-y-conexion.borneras-tornillo"),
    ("UT",       "borneras-y-conexion.borneras-push-in"),
    ("PT",       "borneras-y-conexion.borneras-push-in"),
    ("STTB",     "borneras-y-conexion.borneras-push-in"),
    ("ST",       "borneras-y-conexion.borneras-push-in"),
    ("MBK",      "borneras-y-conexion.borneras-tornillo"),
    ("KH",       "borneras-y-conexion.borneras-tornillo"),
    ("GUS",      "borneras-y-conexion.borneras-tornillo"),
    ("TW",       "borneras-y-conexion.borneras-tornillo"),
    ("PWO",      "borneras-y-conexion.borneras-tornillo"),
    ("PW",       "borneras-y-conexion.borneras-tornillo"),

    # Borneras PCB tornillo (greedy: variantes largas primero)
    ("ZFKKDSA",  "borneras-y-conexion.borneras-pcb"),
    ("ZFK4DSA",  "borneras-y-conexion.borneras-pcb"),
    ("ZFK3DSA",  "borneras-y-conexion.borneras-pcb"),
    ("ZFKDSA",   "borneras-y-conexion.borneras-pcb"),
    ("ZFKDS",    "borneras-y-conexion.borneras-pcb"),
    ("FFKDS",    "borneras-y-conexion.borneras-pcb"),
    ("MK3DSMH",  "borneras-y-conexion.borneras-pcb"),
    ("MK3DSH",   "borneras-y-conexion.borneras-pcb"),
    ("MK3DS",    "borneras-y-conexion.borneras-pcb"),
    ("SMKDS",    "borneras-y-conexion.borneras-pcb"),
    ("MKKDS",    "borneras-y-conexion.borneras-pcb"),
    ("MKDSP",    "borneras-y-conexion.borneras-pcb"),
    ("MKDS",     "borneras-y-conexion.borneras-pcb"),
    ("GMKDS",    "borneras-y-conexion.borneras-pcb"),
    ("GMSTB",    "borneras-y-conexion.borneras-pcb"),
    ("UMSTB",    "borneras-y-conexion.borneras-pcb"),
    ("MPT",      "borneras-y-conexion.borneras-pcb"),
    ("LPTA",     "borneras-y-conexion.borneras-pcb"),
    ("LPT",      "borneras-y-conexion.borneras-pcb"),
    ("FRONT",    "borneras-y-conexion.borneras-pcb"),
    ("FR",       "borneras-y-conexion.borneras-pcb"),
    ("FS",       "borneras-y-conexion.borneras-pcb"),
    ("PSC",      "borneras-y-conexion.borneras-pcb"),
    ("SDDC",     "borneras-y-conexion.borneras-pcb"),
    ("SDC",      "borneras-y-conexion.borneras-pcb"),
    ("TDPT",     "borneras-y-conexion.borneras-pcb"),

    # Conectores fotovoltaicos (PV)
    ("PV-",      "conectores-industriales.conectores-fotovoltaicos"),
    ("PV ",      "conectores-industriales.conectores-fotovoltaicos"),
    ("PV",       "conectores-industriales.conectores-fotovoltaicos"),

    # Power supplies
    ("QUINT",    "fuentes-alimentacion.fuentes-dc-industriales"),
    ("TRIO",     "fuentes-alimentacion.fuentes-dc-industriales"),
    ("UNO",      "fuentes-alimentacion.fuentes-dc-industriales"),
    ("STEP",     "fuentes-alimentacion.fuentes-dc-industriales"),
    ("MINI POW", "fuentes-alimentacion.fuentes-dc-industriales"),

    # SPD / Surge / DPS
    ("VAL-",     "proteccion-circuitos.dps-sobretension"),
    ("VAL ",     "proteccion-circuitos.dps-sobretension"),
    ("PLUGTRAB", "proteccion-circuitos.dps-sobretension"),
    ("CT-",      "proteccion-circuitos.dps-sobretension"),
    ("CTM",      "proteccion-circuitos.dps-sobretension"),
    ("TRABTECH", "proteccion-circuitos.dps-sobretension"),

    # Reles
    ("EMG",      "reles-y-contactores.reles-acoplamiento"),
    ("RIF-",     "reles-y-contactores.reles-acoplamiento"),
    ("PSR",      "reles-y-contactores.reles-seguridad"),
    ("PLC-",     "reles-y-contactores.reles-acoplamiento"),

    # Switches / comunicacion
    ("FL SWITCH", "comunicacion-industrial.switches-ethernet"),
    ("FL-SWITCH", "comunicacion-industrial.switches-ethernet"),
    ("FL ETH",   "comunicacion-industrial.switches-ethernet"),
    ("FL-ETH",   "comunicacion-industrial.switches-ethernet"),
    ("FL NAT",   "comunicacion-industrial.seguridad-red"),
    ("FL-NAT",   "comunicacion-industrial.seguridad-red"),
    ("FL WLAN",  "comunicacion-industrial.wireless"),
    ("FL-WLAN",  "comunicacion-industrial.wireless"),
    ("RAD-",     "comunicacion-industrial.wireless"),

    # Acondicionamiento / aisladores
    ("MINI MCR", "acondicionamiento-de-senal.aisladores"),
    ("MINI-MCR", "acondicionamiento-de-senal.aisladores"),
    ("MCR-",     "acondicionamiento-de-senal.aisladores"),

    # Disyuntores electronicos
    ("CB E",     "proteccion-circuitos.disyuntores-electronicos"),
    ("CAPAROC",  "proteccion-circuitos.disyuntores-electronicos"),
]

# Fallback: si no hay match en PHOENIX_PREFIX_MAP, usar este leaf
PHOENIX_FALLBACK = "borneras-y-conexion.borneras-pcb"


def assign_phoenix_leaf(model):
    if not model:
        return PHOENIX_FALLBACK
    m = model.upper().strip()
    for prefix, leaf in PHOENIX_PREFIX_MAP:
        if m.startswith(prefix):
            return leaf
    return PHOENIX_FALLBACK


# ---------------------------------------------------------------------------
# Mapeo colsein-online por (brand, sub-categoria)
# ---------------------------------------------------------------------------
# Llave: el segundo y tercer segmento del leaf id (brand.subcat)
COLSEIN_SUBCAT_MAP = {
    # Unitronics PLCs
    "unitronics.vision":        "control-automatizacion.oplc.vision-unistream",
    "unitronics.unistream":     "control-automatizacion.oplc.vision-unistream",
    "unitronics.jazz":          "control-automatizacion.oplc.jazz-samba",
    "unitronics.samba":         "control-automatizacion.oplc.jazz-samba",
    "unitronics.motion-control": "motores-movimiento.variadores",
    "unitronics.accesorios-unitronics": "control-automatizacion.oplc.vision-unistream",

    # Red Lion
    "red-lion.indication":      "hmi-visualizacion.hmi-fisica",
    "red-lion.general":         "hmi-visualizacion.hmi-fisica",
    "red-lion.networking":      "comunicacion-industrial.switches-ethernet",
    "red-lion.interface":       "acondicionamiento-de-senal.aisladores",

    # ABB
    "abb.interruptores":        "proteccion-circuitos.magnetotermicos",
    "abb.mando-y-senalizacion": "hmi-visualizacion.hmi-fisica",
    "abb.variadores-de-velocidad-y-accesorios": "motores-movimiento.variadores",
    "abb.cofres-metalicos":     "mecanica-estructura.mesas-estaciones",
    "abb.contactores":          "reles-y-contactores.contactores",
    "abb.reles-termicos":       "reles-y-contactores.contactores",

    # SICK (sub-cat sub-bucket dentro de deteccion-posicionamiento)
    "sick.general":                 "deteccion-posicionamiento.sensores-distancia",
    "sick.sensores-fotoelectricos": "deteccion-posicionamiento.fotoelectricos-g6-compactos",
    "sick.sensores-inductivos":     "deteccion-posicionamiento.sensores-inductivos",
    "sick.sensores-de-distancia":   "deteccion-posicionamiento.sensores-distancia",
    "sick.sensores-de-registro":    "deteccion-posicionamiento.sensores-contraste",
    "sick.controladores-de-seguridad": "seguridad-maquina-industrial.controladores-seguridad",
    "sick.interruptores-de-seguridad": "seguridad-maquina-industrial.interruptores-seguridad",
    "sick.reles-de-seguridad":      "reles-y-contactores.reles-seguridad",
    "sick.encoder":                 "deteccion-posicionamiento.encoders.incrementales",
    "sick.conectores-y-cables":     "deteccion-posicionamiento.cables-conexion",
    "sick.accesorios":              "deteccion-posicionamiento.cables-conexion",

    # HBK / Janitza / WEG / Troax / Helukabel / Advantech
    "hbk.celdas-de-carga":      "instrumentacion-medicion.fuerza-peso.celdas-carga",
    "janitza.medidores-de-energia": "monitoreo-de-energia.medidores",
    "janitza.general":          "monitoreo-de-energia.medidores",
    "weg.motor-trifasico":      "motores-movimiento.motores",
    "troax.paneles":            "seguridad-maquina-industrial.paneles-malla",
    "troax.cerraduras":         "seguridad-maquina-industrial.paneles-malla",
    "troax.postes":             "seguridad-maquina-industrial.paneles-malla",
    "troax.accesorios-troax":   "seguridad-maquina-industrial.paneles-malla",
    "helukabel.cables":         "cables-conexion.cables.control-poder",
    "advantech.pc-industriales": "computo-industrial.ipc-rack",
    "advantech.modulos-de-e-s-remotas": "control-automatizacion.io-remoto",
    "advantech.conectividad":   "comunicacion-industrial.pasarelas-convertidores",
    "advantech.general":        "computo-industrial.ipc-rack",

    # Phoenix Contact (anidado dentro de colsein-online)
    "phoenix-contact.conectividad-industrial-en-gabinetes-icc": "borneras-y-conexion.borneras-tornillo",
    "phoenix-contact.conectividad-industrial-en-campo-ifc":     "conectores-industriales.conectores-circulares-m8-m12",
    "phoenix-contact.componentes-de-interfaz-if":                "reles-y-contactores.reles-acoplamiento",
    "phoenix-contact.fuentes-de-alimentacion-ps":                "fuentes-alimentacion.fuentes-dc-industriales",
    "phoenix-contact.herramientas":                              "herramientas-industriales.crimpadoras",
    "phoenix-contact.trabtech-tt":                               "proteccion-circuitos.dps-sobretension",
    "phoenix-contact.general":                                   "borneras-y-conexion.borneras-tornillo",
}


def assign_colsein_leaf(leaf):
    """Para 'colsein-online.<brand>.<subcat>' busca por tupla (brand, subcat)."""
    parts = (leaf or "").split(".")
    if len(parts) < 2:
        return None
    if parts[0] != "colsein-online":
        return None
    key = ".".join(parts[1:3]) if len(parts) >= 3 else parts[1]
    return COLSEIN_SUBCAT_MAP.get(key)


# ---------------------------------------------------------------------------
# Wire / HTTP helpers
# ---------------------------------------------------------------------------
def http_post(path, body, headers=None):
    url = BASE_URL + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def admin_login():
    if not ADMIN_USER or not ADMIN_PASS:
        sys.exit("Faltan ADMIN_USER / ADMIN_PASS en el entorno")
    code, body = http_post("/api/admin/login",
                           {"user": ADMIN_USER, "password": ADMIN_PASS})
    if code != 200 or not body.get("token"):
        sys.exit(f"Login admin fallo: {code} {body}")
    return body["token"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra el plan, no envia nada al servidor")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--keep-nodes", action="store_true",
                        help="Solo reasigna; no borra los nodos phoenix-contact / colsein-online")
    args = parser.parse_args()

    print(f"[1/4] Descargando productos de {BASE_URL}/api/products ...")
    prods = json.loads(urllib.request.urlopen(
        BASE_URL + "/api/products", timeout=60).read())
    print(f"      {len(prods)} productos en total")

    targets = []
    for p in prods:
        leaf = p.get("leaf") or ""
        if leaf.startswith("phoenix-contact"):
            new_leaf = assign_phoenix_leaf(p.get("model"))
        elif leaf.startswith("colsein-online"):
            new_leaf = assign_colsein_leaf(leaf)
        else:
            continue
        if not new_leaf or new_leaf == leaf:
            continue
        targets.append((p, new_leaf))

    print(f"[2/4] {len(targets)} productos a reasignar")
    by_dest = Counter(nl for _, nl in targets)
    print("      Distribucion por hoja destino:")
    for dest, n in sorted(by_dest.items(), key=lambda kv: -kv[1]):
        print(f"        {n:5d}  {dest}")

    payload_products = []
    for p, new_leaf in targets:
        cp = {
            "id": p["id"],
            "brand": p.get("brand"),
            "model": p.get("model"),
            "name": p.get("name"),
            "family": p.get("family"),
            "leaf": new_leaf,
            "secondary_leaves": [],
            "desc": p.get("description") or p.get("desc"),
            "url": p.get("manufacturer_url") or p.get("url"),
            "lifecycle": p.get("lifecycle") or "active",
            "is_software": p.get("is_software", 0),
        }
        for k, v in (p.get("attributes") or {}).items():
            cp.setdefault(k, v)
        payload_products.append(cp)

    if args.dry_run:
        print("\n[dry-run] No se envia nada. Ejemplos:")
        for p, nl in targets[:5]:
            print(f"  {p.get('id')}  {p.get('leaf')}  ->  {nl}")
        return

    token = admin_login()
    headers = {"X-Admin-Token": token}

    print(f"[3/4] Subiendo en chunks de {args.chunk_size} ...")
    inserted = updated = skipped = 0
    for i in range(0, len(payload_products), args.chunk_size):
        chunk = payload_products[i:i + args.chunk_size]
        code, body = http_post("/api/admin/import-products-batch",
                               {"products": chunk}, headers)
        if code != 200:
            sys.exit(f"chunk {i} fallo: {code} {body}")
        inserted += body.get("inserted", 0)
        updated += body.get("updated", 0)
        skipped += body.get("skipped", 0)
        print(f"      chunk {i//args.chunk_size + 1}: "
              f"+{body.get('inserted', 0)} ins, +{body.get('updated', 0)} upd, "
              f"{body.get('skipped', 0)} skp")
    print(f"      total: {inserted} insertados, {updated} actualizados, {skipped} omitidos")

    if args.keep_nodes:
        print("[4/4] --keep-nodes: no se borran nodos.")
        return

    print("[4/4] Borrando trunks phoenix-contact y colsein-online ...")
    code, body = http_post("/api/admin/delete-nodes",
                           {"trunks": ["phoenix-contact", "colsein-online"]},
                           headers)
    if code != 200:
        sys.exit(f"delete-nodes fallo: {code} {body}")
    print(f"      {body.get('removed_count')} nodos borrados, "
          f"productos huerfanos: {body.get('orphan_products')}")
    print("LISTO.")


if __name__ == "__main__":
    main()
