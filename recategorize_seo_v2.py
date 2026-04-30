"""V2: Mueve los 2,471 productos restantes de phoenix-contact.catalogo-general
a las hojas SEO basandose en prefijos del modelo, sin tocar los productos ya
re-categorizados.
"""
import urllib.request
import json
import re
from collections import defaultdict


# Mapeo: prefijo -> hoja SEO destino
# Orden: prefijos largos primero (matching greedy)
PREFIX_TO_SEO = [
    # Bornas PCB tornillo (MKDS, GMSTB y derivadas)
    ("SMKDS",    "borneras-y-conexion.borneras-pcb"),
    ("MKKDS",    "borneras-y-conexion.borneras-pcb"),
    ("MDSTBV",   "borneras-y-conexion.borneras-pcb-vertical"),
    ("MDSTB",    "borneras-y-conexion.borneras-pcb"),
    ("GMSTBVA",  "borneras-y-conexion.borneras-pcb-vertical"),
    ("GMSTBV",   "borneras-y-conexion.borneras-pcb-vertical"),
    ("GMSTBA",   "borneras-y-conexion.borneras-pcb-vertical"),
    ("GMSTB",    "borneras-y-conexion.borneras-pcb"),
    ("GMVSTBR",  "borneras-y-conexion.borneras-pcb-vertical"),
    ("GMVSTBW",  "borneras-y-conexion.borneras-pcb-vertical"),
    ("UMSTBVK",  "borneras-y-conexion.borneras-pcb-vertical"),
    ("UMSTB",    "borneras-y-conexion.borneras-pcb"),
    ("ZFKDSA",   "borneras-y-conexion.borneras-pcb"),
    ("ZFKDS",    "borneras-y-conexion.borneras-pcb"),
    ("TDPT",     "borneras-y-conexion.borneras-pcb"),
    # Conectores macho/hembra
    ("DFK-MSTB", "conectores-industriales.conectores-pcb"),
    ("DFK-PC",   "conectores-industriales.conectores-pcb"),
    ("DFMC",     "conectores-industriales.conectores-pcb"),
    ("FKIC",     "conectores-industriales.conectores-pcb"),
    ("GICV",     "conectores-industriales.conectores-pcb"),
    ("GIC",      "conectores-industriales.conectores-pcb"),
    ("XPC",      "conectores-industriales.conectores-pcb"),
    ("ISPC",     "conectores-industriales.conectores-pcb"),
    ("TSPC",     "conectores-industriales.conectores-pcb"),
    ("IMC",      "conectores-industriales.conectores-pcb"),
    ("ZEC",      "conectores-industriales.conectores-pcb"),
    # Power-related (DD/D series son bornas alta corriente)
    ("DD32H",    "borneras-y-conexion.borneras-alta-corriente"),
    ("DD31H",    "borneras-y-conexion.borneras-alta-corriente"),
    ("DD21H",    "borneras-y-conexion.borneras-alta-corriente"),
    ("D32H",     "borneras-y-conexion.borneras-alta-corriente"),
    ("D31H",     "borneras-y-conexion.borneras-alta-corriente"),
    # Otros - general fallback
    ("FR",       "borneras-y-conexion.borneras-pcb"),  # FRONT-related
    ("FFKDS",    "borneras-y-conexion.borneras-pcb"),
    # Power supplies
    ("QUINT",    "fuentes-alimentacion.fuentes-dc-industriales"),
    ("TRIO",     "fuentes-alimentacion.fuentes-dc-industriales"),
    ("UNO",      "fuentes-alimentacion.fuentes-dc-industriales"),
    ("STEP",     "fuentes-alimentacion.fuentes-dc-industriales"),
    ("MINI POW", "fuentes-alimentacion.fuentes-dc-industriales"),
    # Surge / DPS
    ("VAL-",     "proteccion-circuitos.dps-sobretension"),
    ("VAL ",     "proteccion-circuitos.dps-sobretension"),
    ("PLUGTRAB", "proteccion-circuitos.dps-sobretension"),
    ("CT-",      "proteccion-circuitos.dps-sobretension"),
    ("CTM",      "proteccion-circuitos.dps-sobretension"),
    # Reles
    ("EMG",      "reles-y-contactores.reles-acoplamiento"),
    ("RIF-",     "reles-y-contactores.reles-acoplamiento"),
    ("PSR",      "reles-y-contactores.reles-seguridad"),
    # Switches
    ("FL SWITCH", "comunicacion-industrial.switches-ethernet"),
    ("FL-SWITCH", "comunicacion-industrial.switches-ethernet"),
    ("FL ETH",   "comunicacion-industrial.switches-ethernet"),
    ("FL-ETH",   "comunicacion-industrial.switches-ethernet"),
    ("FL NAT",   "comunicacion-industrial.seguridad-red"),
    ("FL-NAT",   "comunicacion-industrial.seguridad-red"),
    # Wireless
    ("FL WLAN",  "comunicacion-industrial.wireless"),
    ("FL-WLAN",  "comunicacion-industrial.wireless"),
    ("RAD-",     "comunicacion-industrial.wireless"),
    # Acondicionamiento
    ("MINI MCR", "acondicionamiento-de-senal.aisladores"),
    ("MINI-MCR", "acondicionamiento-de-senal.aisladores"),
    ("MCR-",     "acondicionamiento-de-senal.aisladores"),
    # CAPAROC
    ("CB E",     "proteccion-circuitos.disyuntores-electronicos"),
    ("CAPAROC",  "proteccion-circuitos.disyuntores-electronicos"),
]


def assign_seo_leaf(model):
    if not model: return None
    m = model.upper().strip()
    for prefix, leaf in PREFIX_TO_SEO:
        if m.startswith(prefix):
            return leaf
    return None


def main():
    print("Loading products...")
    prods = json.loads(urllib.request.urlopen(
        "https://web-production-f7337.up.railway.app/api/products").read())
    cg = [p for p in prods if p.get("leaf") == "phoenix-contact.catalogo-general"]
    print(f"  {len(cg)} en catalogo-general")

    new_assignments = []
    by_new = defaultdict(int)
    no_match = 0
    for p in cg:
        new_leaf = assign_seo_leaf(p.get("model", ""))
        if not new_leaf:
            no_match += 1
            continue
        cp = {
            "id": p["id"],
            "brand": p["brand"],
            "model": p.get("model"),
            "name": p.get("name"),
            "family": p.get("family"),
            "leaf": new_leaf,
            "secondary_leaves": [],
            "desc": p.get("desc"),
            "url": p.get("url"),
            "lifecycle": p.get("lifecycle", "active"),
            "is_software": p.get("is_software", 0),
        }
        for k, v in (p.get("attributes") or {}).items():
            cp[k] = v
        new_assignments.append(cp)
        by_new[new_leaf] += 1

    print(f"  Re-asignados: {len(new_assignments)}")
    print(f"  Sin match (quedan en catalogo-general): {no_match}")
    print()
    print("Por nueva hoja SEO:")
    for leaf, n in sorted(by_new.items(), key=lambda kv: -kv[1]):
        print(f"  {leaf}: +{n}")

    import os
    os.makedirs("seo_v2_chunks", exist_ok=True)
    chunk_size = 1500
    for i in range(0, len(new_assignments), chunk_size):
        chunk = new_assignments[i:i + chunk_size]
        cn = i // chunk_size + 1
        with open(f"seo_v2_chunks/chunk_{cn:02d}.json", "w", encoding="utf-8") as f:
            json.dump({"products": chunk}, f, ensure_ascii=False)
    print(f"  {(len(new_assignments) + chunk_size - 1) // chunk_size} chunks")


if __name__ == "__main__":
    main()
