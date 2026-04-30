"""Re-categoriza los 9843 productos Phoenix 'catalogo-general' en hojas
mas especificas basadas en el prefix del modelo. Tambien extrae el 'paso'
de conexion del modelo cuando aplica.
"""
import urllib.request
import json
import re
from collections import defaultdict


# Mapeo: prefijos de modelo -> (leaf_id, leaf_label)
# El orden importa: prefijos mas largos primero (matching greedy).
PREFIX_TO_LEAF = [
    # Bornas PCB (terminal blocks for PCB)
    ("SMKDSN", ("phoenix-contact.bornas-pcb-mkds", "Bornas PCB MKDS")),
    ("MKDS",   ("phoenix-contact.bornas-pcb-mkds", "Bornas PCB MKDS")),
    ("SMSTB",  ("phoenix-contact.bornas-pcb-mstb-mini", "Bornas PCB MSTB mini")),
    ("MSTBVA", ("phoenix-contact.bornas-pcb-mstb-vertical", "Bornas PCB MSTB vertical/angular")),
    ("MSTBV",  ("phoenix-contact.bornas-pcb-mstb-vertical", "Bornas PCB MSTB vertical/angular")),
    ("MSTBA",  ("phoenix-contact.bornas-pcb-mstb-vertical", "Bornas PCB MSTB vertical/angular")),
    ("MSTBC",  ("phoenix-contact.bornas-pcb-mstb-vertical", "Bornas PCB MSTB vertical/angular")),
    ("MVSTB",  ("phoenix-contact.bornas-pcb-mstb-vertical", "Bornas PCB MSTB vertical/angular")),
    ("MSTB",   ("phoenix-contact.bornas-pcb-mstb", "Bornas PCB MSTB")),
    ("DMCV",   ("phoenix-contact.bornas-pcb-dmc", "Bornas PCB DMC")),
    ("DMC",    ("phoenix-contact.bornas-pcb-dmc", "Bornas PCB DMC")),
    ("FKC",    ("phoenix-contact.conectores-pcb-resorte", "Conectores PCB con resorte")),
    ("FK-MCP", ("phoenix-contact.conectores-pcb-resorte", "Conectores PCB con resorte")),
    ("FMC",    ("phoenix-contact.conectores-pcb-resorte", "Conectores PCB con resorte")),
    ("FRONT",  ("phoenix-contact.bornas-pcb-front", "Bornas PCB FRONT")),
    # COMBICON conectores macho/hembra
    ("MCDNV",  ("phoenix-contact.combicon-conectores-mc", "Conectores COMBICON MC")),
    ("MCDN",   ("phoenix-contact.combicon-conectores-mc", "Conectores COMBICON MC")),
    ("MCVR",   ("phoenix-contact.combicon-conectores-mcv", "Conectores COMBICON MCV")),
    ("MCVW",   ("phoenix-contact.combicon-conectores-mcv", "Conectores COMBICON MCV")),
    ("MCV",    ("phoenix-contact.combicon-conectores-mcv", "Conectores COMBICON MCV")),
    ("MC",     ("phoenix-contact.combicon-conectores-mc", "Conectores COMBICON MC")),
    # Conectores varietales
    ("PCH",    ("phoenix-contact.combicon-bases-pc", "Bases COMBICON PC")),
    ("PCV",    ("phoenix-contact.combicon-bases-pc", "Bases COMBICON PC")),
    ("PCSM",   ("phoenix-contact.combicon-bases-pc", "Bases COMBICON PC")),
    ("PCT",    ("phoenix-contact.combicon-bases-pc", "Bases COMBICON PC")),
    ("PC",     ("phoenix-contact.combicon-bases-pc", "Bases COMBICON PC")),
    ("IPC",    ("phoenix-contact.combicon-bases-ic", "Bases COMBICON IC")),
    ("LPC",    ("phoenix-contact.combicon-bases-ic", "Bases COMBICON IC")),
    ("IC",     ("phoenix-contact.combicon-bases-ic", "Bases COMBICON IC")),
    ("PTSM",   ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PSTPC",  ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PSTPV",  ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PST",    ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PTM",    ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PTRV",   ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PTPM",   ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PTPV",   ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PTPB",   ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("PT",     ("phoenix-contact.bornas-pcb-pt", "Bornas PCB serie PT")),
    ("SPTAF",  ("phoenix-contact.bornas-pcb-spt", "Bornas PCB SPT")),
    ("SPT-THR",("phoenix-contact.bornas-pcb-spt", "Bornas PCB SPT")),
    ("SPTA",   ("phoenix-contact.bornas-pcb-spt", "Bornas PCB SPT")),
    ("SPT",    ("phoenix-contact.bornas-pcb-spt", "Bornas PCB SPT")),
    ("SPC",    ("phoenix-contact.bornas-pcb-spt", "Bornas PCB SPT")),
    ("CCA",    ("phoenix-contact.cca-conectores", "Conectores CCA")),
    ("CC",     ("phoenix-contact.cca-conectores", "Conectores CCA")),
    ("FP",     ("phoenix-contact.bornas-front-pcb", "Bornas FRONT PCB FP")),
]


def extract_pitch_mm(model):
    """Extrae el paso (pitch) en mm del modelo Phoenix.
    Patrones: '...3,5', '...3,81', '...5,08', '...7,62'
    """
    m = re.search(r"-(\d{1,2}(?:[\.,]\d{1,2})?)\s*$", model.strip())
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except: return None
    return None


def get_leaf_for_model(model):
    """Determina el leaf basado en el prefijo del modelo."""
    if not model:
        return None
    m = model.upper().strip()
    for prefix, (leaf, label) in PREFIX_TO_LEAF:
        if m.startswith(prefix):
            return leaf, label
    return None


def main():
    print("Loading products from Railway...")
    prods = json.loads(urllib.request.urlopen(
        "https://web-production-f7337.up.railway.app/api/products").read())
    phoenix_general = [p for p in prods
                       if p.get("leaf") == "phoenix-contact.catalogo-general"]
    print(f"  {len(phoenix_general)} productos en catalogo-general")

    # Re-categorizar
    new_assignments = []  # [(product_id, new_leaf, pitch_mm), ...]
    leaf_label_map = {}  # leaf_id -> label
    no_match_count = 0
    by_new_leaf = defaultdict(int)
    pitch_count = 0

    for p in phoenix_general:
        match = get_leaf_for_model(p.get("model", ""))
        if not match:
            no_match_count += 1
            continue
        new_leaf, label = match
        leaf_label_map[new_leaf] = label
        pitch = extract_pitch_mm(p.get("model", ""))
        new_assignments.append({
            "id": p["id"],
            "leaf": new_leaf,
            "pitch_mm": pitch,
            "model": p.get("model"),
            "name": p.get("name"),
            "brand": p.get("brand"),
            "family": p.get("family"),
            "desc": p.get("desc"),
            "url": p.get("url"),
            "lifecycle": p.get("lifecycle", "active"),
            "is_software": p.get("is_software", 0),
            # Mantener atributos existentes
            **{k: v for k, v in (p.get("attributes") or {}).items()},
        })
        by_new_leaf[new_leaf] += 1
        if pitch:
            pitch_count += 1

    print(f"  Re-categorizados: {len(new_assignments)}")
    print(f"  Sin match (quedan en catalogo-general): {no_match_count}")
    print(f"  Con pitch extraido: {pitch_count}")
    print()
    print(f"Distribucion por nueva hoja:")
    for leaf, n in sorted(by_new_leaf.items(), key=lambda kv: -kv[1]):
        print(f"  {leaf}: {n}")

    # Construir payloads
    # 1. Nodos para registrar
    nodes = []
    for leaf, label in leaf_label_map.items():
        nodes.append({
            "id": leaf,
            "label": label,
            "parent": "phoenix-contact",
            "is_leaf": True,
        })

    # 2. Definicion de pitch_mm como attribute
    definitions = {
        "pitch_mm": {"label": "Paso (mm)", "kind": "enum", "field": "pitch_mm"},
    }

    # 3. Filtros sugeridos por hoja: pitch, polos, voltaje
    leaf_filters = {}
    for leaf in leaf_label_map:
        leaf_filters[leaf] = ["pitch_mm", "voltaje_dc", "voltaje_ac", "corriente_a", "calibre_awg"]

    register_payload = {
        "nodes": nodes,
        "definitions": definitions,
        "leaf_filters": leaf_filters,
    }
    with open("phoenix_recat_register.json", "w", encoding="utf-8") as f:
        json.dump(register_payload, f, ensure_ascii=False)
    print(f"\nSaved phoenix_recat_register.json ({len(nodes)} nodos, "
          f"{len(definitions)} defs, {len(leaf_filters)} leaves)")

    # 4. Productos batch (para upsert con nuevo leaf y nuevo atributo)
    # Limpiar para que el endpoint los acepte
    clean = []
    for p in new_assignments:
        cp = {
            "id": p["id"],
            "brand": p["brand"],
            "model": p["model"],
            "name": p["name"],
            "family": p.get("family"),
            "leaf": p["leaf"],
            "secondary_leaves": [],
            "desc": p.get("desc"),
            "url": p.get("url"),
            "lifecycle": p.get("lifecycle"),
            "is_software": p.get("is_software"),
        }
        # Atributos planos
        for k, v in p.items():
            if k in ("id", "brand", "model", "name", "family", "leaf",
                     "secondary_leaves", "desc", "url", "lifecycle", "is_software",
                     "pitch_mm"):
                continue
            cp[k] = v
        if p.get("pitch_mm") is not None:
            cp["pitch_mm"] = p["pitch_mm"]
        clean.append(cp)

    # Chunk en lotes de 2000
    import os
    os.makedirs("phoenix_recat_chunks", exist_ok=True)
    chunk_size = 2000
    for i in range(0, len(clean), chunk_size):
        chunk = clean[i:i + chunk_size]
        cn = i // chunk_size + 1
        with open(f"phoenix_recat_chunks/chunk_{cn:02d}.json", "w", encoding="utf-8") as f:
            json.dump({"products": chunk}, f, ensure_ascii=False)
    print(f"  {(len(clean) + chunk_size - 1) // chunk_size} chunks listos")


if __name__ == "__main__":
    main()
