"""Re-categoriza TODOS los productos por TIPO DE PRODUCTO (SEO friendly).
Ya no usa el catalogo o serie como hoja: la marca queda como filtro,
la jerarquia es por tipo de producto en espanol/ingles.
"""
import urllib.request
import json
import re
from collections import defaultdict


# =============================================================================
# NUEVA TAXONOMIA por TIPO DE PRODUCTO (SEO-friendly, espanol)
# =============================================================================
NEW_TRUNKS = [
    # (id, label)
    ("borneras-y-conexion", "Borneras y conexión (Terminal blocks)"),
    ("conectores-industriales", "Conectores industriales"),
    ("fuentes-alimentacion", "Fuentes de alimentación (Power supplies)"),
    ("proteccion-circuitos", "Protección de circuitos"),
    ("reles-y-contactores", "Relés y contactores"),
    ("comunicacion-industrial", "Comunicación industrial"),
    ("marcaje-e-identificacion", "Marcaje e identificación"),
    ("acondicionamiento-de-senal", "Acondicionamiento de señal"),
    ("cables-y-distribucion", "Cables y distribución"),
    ("iluminacion-industrial", "Iluminación industrial"),
    ("monitoreo-de-energia", "Monitoreo de energía"),
    ("herramientas-industriales", "Herramientas industriales"),
]

# Sub-hojas dentro de cada trunk nuevo
NEW_LEAVES = [
    # (leaf_id, label, parent)
    # === Borneras ===
    ("borneras-y-conexion.borneras-tornillo", "Borneras DIN tornillo (Screw terminal blocks)", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-push-in", "Borneras DIN push-in / resorte (Spring/push-in terminal blocks)", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-seccionables", "Borneras seccionables (Disconnect / knife terminals)", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-fusible", "Borneras con fusible (Fuse terminal blocks)", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-pcb", "Borneras para PCB (PCB terminal blocks)", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-pcb-vertical", "Borneras PCB vertical / angular", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-alta-corriente", "Borneras alta corriente / power", "borneras-y-conexion"),
    ("borneras-y-conexion.borneras-rapidas", "Borneras de conexión rápida / push", "borneras-y-conexion"),
    # === Conectores ===
    ("conectores-industriales.conectores-pcb", "Conectores PCB enchufables (Pluggable PCB connectors)", "conectores-industriales"),
    ("conectores-industriales.conectores-circulares-m8-m12", "Conectores circulares M8 / M12", "conectores-industriales"),
    ("conectores-industriales.conectores-circulares-m17-m58", "Conectores circulares M17–M58", "conectores-industriales"),
    ("conectores-industriales.conectores-pesados", "Conectores industriales pesados (Heavy duty)", "conectores-industriales"),
    ("conectores-industriales.conectores-datos", "Conectores de datos / Ethernet", "conectores-industriales"),
    ("conectores-industriales.conectores-fotovoltaicos", "Conectores fotovoltaicos (PV)", "conectores-industriales"),
    # === Fuentes de alimentacion ===
    ("fuentes-alimentacion.fuentes-dc-industriales", "Fuentes DC industriales (DIN-rail)", "fuentes-alimentacion"),
    ("fuentes-alimentacion.ups-respaldo", "UPS y energía de respaldo", "fuentes-alimentacion"),
    ("fuentes-alimentacion.convertidores-dc-dc", "Convertidores DC/DC", "fuentes-alimentacion"),
    # === Proteccion de circuitos ===
    ("proteccion-circuitos.dps-sobretension", "Protección contra sobretensión / DPS / SPD", "proteccion-circuitos"),
    ("proteccion-circuitos.disyuntores-electronicos", "Disyuntores electrónicos (CAPAROC y similares)", "proteccion-circuitos"),
    ("proteccion-circuitos.guardamotores", "Guardamotores / disyuntores motor", "proteccion-circuitos"),
    ("proteccion-circuitos.magnetotermicos", "Magnetotérmicos (MCB)", "proteccion-circuitos"),
    # === Reles y contactores ===
    ("reles-y-contactores.reles-acoplamiento", "Relés de acoplamiento (Interface relays)", "reles-y-contactores"),
    ("reles-y-contactores.reles-seguridad", "Relés de seguridad (Safety relays)", "reles-y-contactores"),
    ("reles-y-contactores.modulos-logicos", "Módulos lógicos / temporizadores", "reles-y-contactores"),
    ("reles-y-contactores.contactores", "Contactores y aparatos de conmutación", "reles-y-contactores"),
    # === Comunicacion industrial ===
    ("comunicacion-industrial.switches-ethernet", "Switches Ethernet industrial", "comunicacion-industrial"),
    ("comunicacion-industrial.wireless", "Wireless industrial", "comunicacion-industrial"),
    ("comunicacion-industrial.fieldbus", "Buses de campo / Fieldbus", "comunicacion-industrial"),
    ("comunicacion-industrial.seguridad-red", "Seguridad de red industrial", "comunicacion-industrial"),
    ("comunicacion-industrial.pasarelas-convertidores", "Pasarelas / convertidores de protocolo", "comunicacion-industrial"),
    # === Marcaje ===
    ("marcaje-e-identificacion.impresoras-industriales", "Impresoras industriales", "marcaje-e-identificacion"),
    ("marcaje-e-identificacion.marcadores-cables", "Marcadores de cables", "marcaje-e-identificacion"),
    ("marcaje-e-identificacion.sistemas-marcaje", "Sistemas de marcaje", "marcaje-e-identificacion"),
    # === Cables y distribucion ===
    ("cables-y-distribucion.cables-sensor-actuador", "Cables sensor / actuador", "cables-y-distribucion"),
    ("cables-y-distribucion.bloques-distribuidores", "Bloques distribuidores", "cables-y-distribucion"),
    ("cables-y-distribucion.sistemas-cableado", "Sistemas de cableado", "cables-y-distribucion"),
    # === Misc ===
    ("monitoreo-de-energia.medidores", "Medidores de energía", "monitoreo-de-energia"),
    ("herramientas-industriales.crimpadoras", "Crimpadoras y herramientas de cable", "herramientas-industriales"),
    ("herramientas-industriales.varios", "Otras herramientas", "herramientas-industriales"),
    ("acondicionamiento-de-senal.aisladores", "Aisladores y convertidores señal", "acondicionamiento-de-senal"),
]

# =============================================================================
# MAPEO: hoja Phoenix actual -> hoja SEO nueva
# =============================================================================
PHOENIX_LEAF_TO_SEO = {
    # Borneras PCB (todas las series Phoenix Contact terminales/conectores PCB)
    "phoenix-contact.bornas-pcb-mstb": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-pcb-mstb-vertical": "borneras-y-conexion.borneras-pcb-vertical",
    "phoenix-contact.bornas-pcb-mstb-mini": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-pcb-pt": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-pcb-spt": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-pcb-mkds": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-pcb-dmc": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-pcb-front": "borneras-y-conexion.borneras-pcb",
    "phoenix-contact.bornas-front-pcb": "borneras-y-conexion.borneras-pcb",
    # Conectores PCB
    "phoenix-contact.combicon-conectores-mc": "conectores-industriales.conectores-pcb",
    "phoenix-contact.combicon-conectores-mcv": "conectores-industriales.conectores-pcb",
    "phoenix-contact.combicon-bases-pc": "conectores-industriales.conectores-pcb",
    "phoenix-contact.combicon-bases-ic": "conectores-industriales.conectores-pcb",
    "phoenix-contact.conectores-pcb-resorte": "conectores-industriales.conectores-pcb",
    "phoenix-contact.conectores-pcb": "conectores-industriales.conectores-pcb",
    "phoenix-contact.cca-conectores": "conectores-industriales.conectores-pcb",
    "phoenix-contact.clixtab": "borneras-y-conexion.borneras-rapidas",
    # Bornas DIN (resorte/seccionables)
    "phoenix-contact.terminales": "borneras-y-conexion.borneras-tornillo",
    "phoenix-contact.terminales-clipline": "borneras-y-conexion.borneras-tornillo",
    "phoenix-contact.bornas-resorte-lateral": "borneras-y-conexion.borneras-push-in",
    # Conectores industriales
    "phoenix-contact.conectores-pesados": "conectores-industriales.conectores-pesados",
    "phoenix-contact.conectores-circulares": "conectores-industriales.conectores-circulares-m17-m58",
    "phoenix-contact.conectores-circulares-m12": "conectores-industriales.conectores-circulares-m8-m12",
    "phoenix-contact.conectores-datos": "conectores-industriales.conectores-datos",
    "phoenix-contact.conectores-fotovoltaicos": "conectores-industriales.conectores-fotovoltaicos",
    # Fuentes
    "phoenix-contact.fuentes-alimentacion": "fuentes-alimentacion.fuentes-dc-industriales",
    # Proteccion
    "phoenix-contact.proteccion-sobretension": "proteccion-circuitos.dps-sobretension",
    "phoenix-contact.proteccion-circuito-caparoc": "proteccion-circuitos.disyuntores-electronicos",
    "phoenix-contact.guardamotores": "proteccion-circuitos.guardamotores",
    # Reles
    "phoenix-contact.reles-logica": "reles-y-contactores.reles-acoplamiento",
    "phoenix-contact.aparatos-conmutacion": "reles-y-contactores.contactores",
    # Comunicacion
    "phoenix-contact.ethernet-industrial": "comunicacion-industrial.switches-ethernet",
    "phoenix-contact.wireless-industrial": "comunicacion-industrial.wireless",
    "phoenix-contact.fieldbus": "comunicacion-industrial.fieldbus",
    "phoenix-contact.io-remoto": "comunicacion-industrial.pasarelas-convertidores",
    "phoenix-contact.nse": "comunicacion-industrial.seguridad-red",
    # Marcaje
    "phoenix-contact.impresoras-marcaje": "marcaje-e-identificacion.impresoras-industriales",
    "phoenix-contact.impresoras-thermomark": "marcaje-e-identificacion.impresoras-industriales",
    "phoenix-contact.impresion-movil": "marcaje-e-identificacion.impresoras-industriales",
    "phoenix-contact.marcaje-cables": "marcaje-e-identificacion.marcadores-cables",
    "phoenix-contact.marcaje": "marcaje-e-identificacion.sistemas-marcaje",
    # Cables y distribucion
    "phoenix-contact.distribuidores": "cables-y-distribucion.bloques-distribuidores",
    "phoenix-contact.distribuidores-cableado": "cables-y-distribucion.bloques-distribuidores",
    "phoenix-contact.cableado-sistema": "cables-y-distribucion.sistemas-cableado",
    # Otros
    "phoenix-contact.acondicionamiento-senal": "acondicionamiento-de-senal.aisladores",
    "phoenix-contact.iluminacion": "iluminacion-industrial",  # leaf simple sin sub
    "phoenix-contact.monitoreo-energia": "monitoreo-de-energia.medidores",
    "phoenix-contact.herramientas": "herramientas-industriales.varios",
    "phoenix-contact.proteccion-explosion": "equipos-zonas-ex.hmi-paneles-ex",  # reuse existing
    "phoenix-contact.hmi-ipc": "control-automatizacion.oplc.vision-unistream",  # reuse existing
    "phoenix-contact.instalacion": "borneras-y-conexion.borneras-tornillo",  # default
    # Catalogo general queda como esta (productos no categorizables)
    # "phoenix-contact.catalogo-general": no se mueve
}


def main():
    print("Loading products from Railway...")
    prods = json.loads(urllib.request.urlopen(
        "https://web-production-f7337.up.railway.app/api/products").read())
    print(f"  {len(prods)} productos total")

    # Re-asignar phoenix
    new_assignments = []
    by_old_leaf = defaultdict(int)
    by_new_leaf = defaultdict(int)
    moved = 0

    for p in prods:
        old_leaf = p.get("leaf")
        if old_leaf not in PHOENIX_LEAF_TO_SEO:
            continue
        new_leaf = PHOENIX_LEAF_TO_SEO[old_leaf]
        by_old_leaf[old_leaf] += 1
        by_new_leaf[new_leaf] += 1
        # Construir producto re-asignado
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
        moved += 1

    print(f"\n  Productos a re-asignar: {moved}")
    print(f"\n  Top 15 hojas SEO destino:")
    for l, n in sorted(by_new_leaf.items(), key=lambda kv: -kv[1])[:15]:
        print(f"    {l}: {n}")

    # Construir nodos a registrar (trunks + leaves)
    nodes = []
    for trunk_id, trunk_label in NEW_TRUNKS:
        nodes.append({"id": trunk_id, "label": trunk_label, "parent": "root", "is_leaf": False})
    for leaf_id, leaf_label, parent in NEW_LEAVES:
        nodes.append({"id": leaf_id, "label": leaf_label, "parent": parent, "is_leaf": True})

    # Filtros sugeridos por leaf SEO
    common_filters_borneras = ["pitch_mm", "polos_interruptor", "voltaje_ac", "voltaje_dc",
                                "corriente_a", "calibre_awg", "seccion_mm2"]
    common_filters_conectores = ["pitch_mm", "polos_interruptor", "voltaje_ac",
                                  "corriente_a", "calibre_awg", "ip_rating", "apantallado"]
    common_filters_proteccion = ["voltaje_ac", "voltaje_dc", "corriente_a", "polos_interruptor"]
    common_filters_fuentes = ["voltaje_dc", "voltaje_ac", "corriente_a", "ip_rating"]
    common_filters_comm = ["voltaje_dc", "ip_rating", "ethernet_ports", "comunicacion_extra"]
    common_filters_reles = ["voltaje_dc", "voltaje_ac", "corriente_a", "polos_interruptor"]

    leaf_filters = {}
    for leaf_id, _, _ in NEW_LEAVES:
        if leaf_id.startswith("borneras-y-conexion"):
            leaf_filters[leaf_id] = common_filters_borneras
        elif leaf_id.startswith("conectores-industriales"):
            leaf_filters[leaf_id] = common_filters_conectores
        elif leaf_id.startswith("proteccion-circuitos"):
            leaf_filters[leaf_id] = common_filters_proteccion
        elif leaf_id.startswith("fuentes-alimentacion"):
            leaf_filters[leaf_id] = common_filters_fuentes
        elif leaf_id.startswith("comunicacion-industrial"):
            leaf_filters[leaf_id] = common_filters_comm
        elif leaf_id.startswith("reles-y-contactores"):
            leaf_filters[leaf_id] = common_filters_reles
        else:
            leaf_filters[leaf_id] = ["voltaje_dc", "corriente_a", "ip_rating"]
    # Tambien iluminacion-industrial (trunk como leaf simple)
    nodes.append({"id": "iluminacion-industrial.lamparas-led", "label": "Lámparas LED industriales", "parent": "iluminacion-industrial", "is_leaf": True})
    leaf_filters["iluminacion-industrial.lamparas-led"] = ["voltaje_dc", "ip_rating"]

    register_payload = {
        "nodes": nodes,
        "definitions": {},
        "leaf_filters": leaf_filters,
    }
    with open("seo_register.json", "w", encoding="utf-8") as f:
        json.dump(register_payload, f, ensure_ascii=False)
    print(f"\nSaved seo_register.json: {len(nodes)} nodos, {len(leaf_filters)} hojas con filtros")

    # Productos chunks
    import os
    os.makedirs("seo_recat_chunks", exist_ok=True)
    chunk_size = 2000
    for i in range(0, len(new_assignments), chunk_size):
        chunk = new_assignments[i:i + chunk_size]
        cn = i // chunk_size + 1
        with open(f"seo_recat_chunks/chunk_{cn:02d}.json", "w", encoding="utf-8") as f:
            json.dump({"products": chunk}, f, ensure_ascii=False)
    n_chunks = (len(new_assignments) + chunk_size - 1) // chunk_size
    print(f"  {n_chunks} chunks generados")


if __name__ == "__main__":
    main()
