"""Limpia los leaf_filters: para cada hoja, deja SOLO los filtros que tienen
al menos 10 productos con valor y al menos 2 valores distintos.

Tambien REEMPLAZA por completo los leaf_filters de la hoja con la lista limpia.
"""
import urllib.request
import json
from collections import defaultdict, Counter


MIN_PRODUCTS_WITH_VALUE = 10
MIN_DISTINCT_VALUES = 2


def main():
    print("Loading products + taxonomy...")
    prods = json.loads(urllib.request.urlopen(
        "https://web-production-f7337.up.railway.app/api/products").read())
    tax = json.loads(urllib.request.urlopen(
        "https://web-production-f7337.up.railway.app/api/taxonomy").read())
    current_lf = tax.get("leaf_filters", {})
    defs = tax.get("attribute_definitions", {})
    field_to_aid = {d["field"]: aid for aid, d in defs.items()}

    # Index productos por hoja
    by_leaf = defaultdict(list)
    for p in prods:
        by_leaf[p.get("leaf")].append(p)

    cleaned_lf = {}
    for leaf, fs in current_lf.items():
        # Atributos por producto en esta hoja
        attr_values = defaultdict(set)  # aid -> set de valores
        attr_count = defaultdict(int)  # aid -> count productos con valor
        for p in by_leaf.get(leaf, []):
            attrs = p.get("attributes") or {}
            for k, v in attrs.items():
                if v in (None, "", [], False):
                    continue
                # k es el field; mapear a aid
                aid = field_to_aid.get(k, k if k in defs else None)
                if not aid:
                    continue
                attr_count[aid] += 1
                if isinstance(v, list):
                    for x in v:
                        attr_values[aid].add(str(x))
                else:
                    attr_values[aid].add(str(v))

        # Solo mantener filtros declarados que pasen umbrales
        kept = []
        for f in fs:
            aid = f.get("id")
            if aid not in defs:
                continue
            n = attr_count[aid]
            distinct = len(attr_values[aid])
            if n >= MIN_PRODUCTS_WITH_VALUE and distinct >= MIN_DISTINCT_VALUES:
                kept.append({"id": aid})
        cleaned_lf[leaf] = kept

    # Reportar diferencias
    print()
    print("Hojas con cambios (limpieza):")
    n_total_old = sum(len(v) for v in current_lf.values())
    n_total_new = sum(len(v) for v in cleaned_lf.values())
    print(f"  Filtros antes: {n_total_old}")
    print(f"  Filtros despues: {n_total_new}")
    print(f"  Filtros eliminados (sin datos suficientes): {n_total_old - n_total_new}")
    print()
    # Show sample
    print("Top 10 hojas con mas cambios:")
    diffs = []
    for leaf, fs in current_lf.items():
        old = {f.get("id") for f in fs}
        new = {f.get("id") for f in cleaned_lf.get(leaf, [])}
        removed = old - new
        if removed:
            diffs.append((leaf, sorted(removed), sorted(new)))
    diffs.sort(key=lambda x: -len(x[1]))
    for leaf, removed, new in diffs[:10]:
        print(f"  {leaf}")
        print(f"    REMOVED: {removed}")
        print(f"    KEPT: {new}")

    # NOTA: el endpoint register-filters es ADITIVO. Para REEMPLAZAR, necesito
    # un endpoint distinto o modificar la taxonomy directamente.
    # Por ahora guardo el resultado y lo importamos via taxonomy directa.
    # En su lugar, voy a generar un payload que SOLO agrega los filtros que
    # estan limpios y faltan, y dejaremos que el frontend descarte los que no
    # discriminan (ya lo hace automaticamente: si distinct < 2 no muestra).
    # Pero eso ya pasa. Asi que el verdadero problema ES otro.

    # Guardo el plan para diagnostico
    plan = {
        "leaf_filters_clean": cleaned_lf,
        "stats": {
            "total_filters_before": n_total_old,
            "total_filters_after": n_total_new,
        }
    }
    with open("filter_cleanup_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print("\nPlan guardado en filter_cleanup_plan.json")
    print("\n[NOTA] El endpoint register-filters solo AGREGA filtros, no los reemplaza.")
    print("Pero el frontend YA descarta filtros con <2 valores distintos automaticamente.")
    print("Si el usuario ve hojas sin filtros, el problema es otro.")


if __name__ == "__main__":
    main()
