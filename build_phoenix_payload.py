"""Construye los payloads de Phoenix:
- phoenix_register_payload.json: nodos + filtros nuevos
- phoenix_chunks/chunk_NN.json: products dividido en chunks de 2000

El catalogo trunk 'phoenix-contact' tambien se crea como root node.
"""
import json
import os
from collections import defaultdict


def main():
    products = json.load(open("phoenix_products.json", encoding="utf-8"))["products"]
    print(f"Total productos: {len(products)}")

    # Identificar todos los leaves usados
    leaves_used = sorted(set(p["leaf"] for p in products))
    print(f"Leaves usados: {len(leaves_used)}")

    # Mapeo leaf -> label legible
    leaf_to_label = {}
    for p in products:
        leaf_to_label[p["leaf"]] = p.get("family") or p["leaf"].split(".")[-1].replace("-", " ").title()

    # Construir nodos (incluye trunk phoenix-contact)
    nodes = [{"id": "phoenix-contact", "label": "Phoenix Contact", "parent": "root", "is_leaf": False}]
    for leaf in leaves_used:
        nodes.append({
            "id": leaf,
            "label": leaf_to_label.get(leaf, leaf.split(".")[-1]),
            "parent": "phoenix-contact",
            "is_leaf": True,
        })

    # Filtros sugeridos por leaf — usar attribute_definitions ya existentes
    # Los attrs comunes que vienen del parser: voltaje_dc, voltaje_ac, corriente_a,
    # calibre_awg, seccion_mm2, polos_interruptor, ip_rating, apantallado
    # seccion_mm2 es nuevo, lo definimos abajo
    common_filters_per_leaf = {}
    # Para cada leaf, asignar los filtros que tienen al menos algunos productos con valor
    attrs_per_leaf = defaultdict(lambda: defaultdict(int))
    for p in products:
        leaf = p["leaf"]
        for k, v in p.items():
            if k in ("id", "brand", "model", "name", "family", "leaf",
                     "secondary_leaves", "desc", "url", "image_url",
                     "lifecycle", "is_software", "_page", "_pdf"):
                continue
            if v is None or v == "" or v == [] or v is False:
                continue
            attrs_per_leaf[leaf][k] += 1

    # Filtros conocidos en attribute_definitions (extiendo si nuevos)
    KNOWN_ATTRS = {"voltaje_dc", "voltaje_ac", "voltaje", "corriente_a", "calibre_awg",
                   "polos_interruptor", "ip_rating", "apantallado", "rango_mm",
                   "salida_tipo", "conexion", "tipo_sensor"}
    NEW_DEFS = {
        "seccion_mm2": {"label": "Sección conductor (mm²)", "kind": "enum", "field": "seccion_mm2"},
    }

    leaf_filters = {}
    for leaf, attrs in attrs_per_leaf.items():
        # Solo agregar filtros con al menos 3 productos que los tengan
        candidates = [k for k, n in attrs.items() if n >= 3]
        if candidates:
            leaf_filters[leaf] = candidates

    # Definitions
    definitions = NEW_DEFS

    payload = {
        "nodes": nodes,
        "definitions": definitions,
        "leaf_filters": leaf_filters,
    }
    with open("phoenix_register_payload.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"Saved phoenix_register_payload.json ({len(nodes)} nodos, "
          f"{len(definitions)} defs, {len(leaf_filters)} leaves con filtros)")

    # Limpiar productos: quitar campos privados antes de subir
    clean_products = []
    for p in products:
        cp = {k: v for k, v in p.items() if not k.startswith("_")}
        clean_products.append(cp)

    # Chunkear en lotes de 2000
    os.makedirs("phoenix_chunks", exist_ok=True)
    chunk_size = 2000
    n_chunks = (len(clean_products) + chunk_size - 1) // chunk_size
    for i in range(n_chunks):
        chunk = clean_products[i * chunk_size:(i + 1) * chunk_size]
        with open(f"phoenix_chunks/chunk_{i+1:02d}.json", "w", encoding="utf-8") as f:
            json.dump({"products": chunk}, f, ensure_ascii=False)
        sz = os.path.getsize(f"phoenix_chunks/chunk_{i+1:02d}.json") / 1024 / 1024
        print(f"  chunk_{i+1:02d}.json: {len(chunk)} productos ({sz:.1f} MB)")
    print(f"\nTotal: {n_chunks} chunks listos para upload")


if __name__ == "__main__":
    main()
