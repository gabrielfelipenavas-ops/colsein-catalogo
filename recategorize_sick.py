"""Re-categoriza los 882 productos SICK fotoelectricos en hojas mas finas
y MUEVE los mal-categorizados (IME=inductivos, DBS/DFS=encoders, CLV=lectores
codigo, TBS/KT5/UF=fluidos) a sus hojas correctas.
"""
import urllib.request
import json
import re
from collections import defaultdict


# Mapeo: regex sobre modelo SICK -> (leaf_id, label)
# Orden importa: prefijos especificos primero
SICK_RECAT = [
    # Movimientos de hojas mal categorizadas
    (r"^IME\d+", ("deteccion-posicionamiento.sensores-inductivos", "Sensores inductivos IM (SICK)")),
    (r"^IMI", ("deteccion-posicionamiento.sensores-inductivos", "Sensores inductivos IMI (SICK)")),
    (r"^DBS\d+", ("deteccion-posicionamiento.encoders.absolutos", "Encoders absolutos DBS")),
    (r"^DFS\d+", ("deteccion-posicionamiento.encoders.incrementales", "Encoders incrementales DFS")),
    (r"^DRS\d+", ("deteccion-posicionamiento.encoders.incrementales", "Encoders DRS")),
    (r"^CLV6\d+", ("deteccion-posicionamiento.lectores-codigo", "Escáneres código de barras CLV")),
    (r"^IDM\d+", ("deteccion-posicionamiento.lectores-codigo", "Lectores 2D IDM")),
    (r"^LECTOR", ("deteccion-posicionamiento.lectores-codigo", "Lectores SICK")),
    (r"^TBS", ("instrumentacion-medicion.flujo", "Sensores de flujo TBS")),
    (r"^LFP", ("instrumentacion-medicion.flujo", "Sensores fluido LFP")),
    (r"^LFV", ("instrumentacion-medicion.flujo", "Sensores fluido LFV")),
    (r"^UM\d+", ("instrumentacion-medicion.flujo", "Sensores ultrasónicos UM")),
    (r"^UC\d+", ("instrumentacion-medicion.flujo", "Sensores ultrasónicos UC")),
    (r"^MHF", ("instrumentacion-medicion.flujo", "Sensores fluido MHF")),
    (r"^PBS", ("instrumentacion-medicion.flujo", "Sensores presión PBS")),
    (r"^PBT", ("instrumentacion-medicion.flujo", "Sensores presión PBT")),
    (r"^LFH", ("instrumentacion-medicion.flujo", "Sensores nivel LFH")),
    (r"^UP\d+", ("instrumentacion-medicion.flujo", "Sensores ultrasónicos UP")),
    (r"^KT5", ("deteccion-posicionamiento.sensores-contraste", "Sensores de contraste KT5")),
    (r"^KTM", ("deteccion-posicionamiento.sensores-contraste", "Sensores de contraste KTM")),
    (r"^CSM", ("deteccion-posicionamiento.sensores-color", "Sensores de color CSM")),
    (r"^LUTM", ("deteccion-posicionamiento.sensores-luminiscencia", "Sensores luminiscencia LUTM")),
    (r"^UF", ("deteccion-posicionamiento.sensores-uv", "Sensores UV UF")),
    (r"^WF\d", ("deteccion-posicionamiento.sensores-fibra", "Amplificadores fibra óptica WF")),
    (r"^WLL", ("deteccion-posicionamiento.sensores-fibra", "Sensores fibra óptica WLL")),
    (r"^LL3", ("deteccion-posicionamiento.sensores-fibra", "Fibras ópticas LL3")),
    (r"^ELG", ("deteccion-posicionamiento.rejillas-fotoelectricas", "Rejillas fotoeléctricas ELG")),
    (r"^DOL", ("deteccion-posicionamiento.cables-conexion", "Cables de conexión DOL")),
    # Inspector y vision
    (r"^V2D", ("deteccion-posicionamiento.vision", "Cámaras 2D Inspector")),
    (r"^INSPECTOR", ("deteccion-posicionamiento.vision", "Inspector cámaras")),
    # Fotoelectricos por serie/tamano
    (r"^GTE6|^GTB6|^GL6|^GR6", ("deteccion-posicionamiento.fotoelectricos-g6-compactos", "Fotocélulas G6 compactas")),
    (r"^GL10|^GTE10|^GTB10", ("deteccion-posicionamiento.fotoelectricos-g10", "Fotocélulas G10")),
    (r"^WTB2S|^WSE2|^WL2|^WS2|^W2S", ("deteccion-posicionamiento.fotoelectricos-w-pequenos", "Fotocélulas W pequeños (W2S/W4)")),
    (r"^WTB4S|^WTB4|^WSE4|^WL4|^WS4|^W4", ("deteccion-posicionamiento.fotoelectricos-w-pequenos", "Fotocélulas W pequeños (W2S/W4)")),
    (r"^WTB8|^WTE8|^WSE8|^WL8|^WS8|^W8", ("deteccion-posicionamiento.fotoelectricos-w8", "Fotocélulas W8")),
    (r"^WTB9|^WTE9|^WSE9|^WL9|^WS9|^W9", ("deteccion-posicionamiento.fotoelectricos-w9", "Fotocélulas W9")),
    (r"^WTB11|^WL11|^WS11|^W11", ("deteccion-posicionamiento.fotoelectricos-w11", "Fotocélulas W11")),
    (r"^WTB12|^WL12|^WS12|^W12", ("deteccion-posicionamiento.fotoelectricos-w12", "Fotocélulas W12")),
    (r"^WTB18|^WL18|^WS18|^W18|^WTB280|^WL280|^W280", ("deteccion-posicionamiento.fotoelectricos-w-grandes", "Fotocélulas W grandes (W18/W280)")),
    (r"^GRTE18|^GRL18|^GR18|^GTE18|^GTB18|^V18", ("deteccion-posicionamiento.fotoelectricos-cilindricos-m18", "Fotocélulas cilíndricas M18")),
    (r"^V180", ("deteccion-posicionamiento.fotoelectricos-cilindricos-m18", "Fotocélulas cilíndricas M18")),
    # Magneticos
    (r"^MZC|^RZC|^MZT|^RZT|^MMS", ("deteccion-posicionamiento.sensores-magneticos", "Sensores magnéticos cilindros")),
    # Capacitivos
    (r"^CM18|^CM30|^CQ", ("deteccion-posicionamiento.sensores-capacitivos", "Sensores capacitivos CM/CQ")),
    # Inductivos adicionales
    (r"^IM\d", ("deteccion-posicionamiento.sensores-inductivos", "Sensores inductivos IM")),
    (r"^IQ", ("deteccion-posicionamiento.sensores-inductivos", "Sensores inductivos IQ")),
    (r"^IMF", ("deteccion-posicionamiento.sensores-inductivos", "Sensores inductivos IMF")),
    # Distancia
    (r"^OD", ("deteccion-posicionamiento.sensores-distancia", "Sensores distancia OD")),
    (r"^DT|^DL", ("deteccion-posicionamiento.sensores-distancia", "Sensores distancia DT/DL")),
    (r"^DX35|^DX50", ("deteccion-posicionamiento.sensores-distancia", "Sensores distancia Dx35/Dx50")),
    # LiDAR
    (r"^LMS|^TIM|^MRS", ("deteccion-posicionamiento.lidar-2d", "Escáneres láser LMS/TIM")),
    # Seguridad
    (r"^S300|^S3000", ("seguridad-maquina-industrial.escaner-laser-seguridad", "Escáneres láser de seguridad S300")),
    (r"^DETEC|^MINITWIN|^M4000|^L41|^L21", ("seguridad-maquina-industrial.cortinas-luz", "Cortinas/escáneres seguridad")),
    (r"^V300", ("seguridad-maquina-industrial.cortinas-luz", "Cortinas/escáneres seguridad")),
    # Interruptores seguridad
    (r"^I12|^I16|^I17|^I10|^RE1|^RE2|^TR4|^IN3000|^IN4000", ("seguridad-maquina-industrial.interruptores-seguridad", "Interruptores de seguridad")),
    # Control seguridad
    (r"^FLEXI|^UE10|^UE23|^UE48|^UE410|^SPEED MON|^STANDSTILL", ("seguridad-maquina-industrial.controladores-seguridad", "Controladores de seguridad")),
]


def get_leaf_for_sick(model):
    if not model:
        return None
    m = model.upper().strip()
    for pattern, (leaf, label) in SICK_RECAT:
        if re.match(pattern, m):
            return leaf, label
    return None


def main():
    print("Loading products from Railway...")
    prods = json.loads(urllib.request.urlopen(
        "https://web-production-f7337.up.railway.app/api/products").read())
    # Tomar TODOS los SICK que estan en la hoja generica de fotoelectricos
    sick_in_foto = [p for p in prods
                    if p.get("brand") == "sick"
                    and p.get("leaf") == "deteccion-posicionamiento.fotoelectricos"]
    print(f"  {len(sick_in_foto)} SICK en hoja generica fotoelectricos")

    new_assignments = []
    leaf_label_map = {}
    by_new_leaf = defaultdict(int)
    no_match = 0

    for p in sick_in_foto:
        match = get_leaf_for_sick(p.get("model", ""))
        if not match:
            no_match += 1
            continue
        new_leaf, label = match
        # Si la hoja nueva es la misma, skip
        if new_leaf == p.get("leaf"):
            continue
        leaf_label_map[new_leaf] = label
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
        # Atributos
        for k, v in (p.get("attributes") or {}).items():
            cp[k] = v
        new_assignments.append(cp)

    print(f"  Re-categorizados: {len(new_assignments)}")
    print(f"  Sin match (quedan en fotoelectricos genericos): {no_match}")
    print()
    print("Distribucion por nueva hoja:")
    for leaf, n in sorted(by_new_leaf.items(), key=lambda kv: -kv[1]):
        print(f"  {leaf}: {n}")

    # Construir nodos a registrar (solo los que no son hojas existentes)
    EXISTING_LEAVES = {
        "deteccion-posicionamiento.sensores-inductivos",
        "deteccion-posicionamiento.sensores-capacitivos",
        "deteccion-posicionamiento.sensores-magneticos",
        "deteccion-posicionamiento.sensores-distancia",
        "deteccion-posicionamiento.lectores-codigo",
        "deteccion-posicionamiento.encoders.absolutos",
        "deteccion-posicionamiento.encoders.incrementales",
        "deteccion-posicionamiento.lidar-2d",
        "deteccion-posicionamiento.vision",
        "instrumentacion-medicion.flujo",
        "seguridad-maquina-industrial.cortinas-luz",
        "seguridad-maquina-industrial.escaner-laser-seguridad",
        "seguridad-maquina-industrial.interruptores-seguridad",
        "seguridad-maquina-industrial.controladores-seguridad",
    }
    nodes = []
    for leaf, label in leaf_label_map.items():
        if leaf in EXISTING_LEAVES:
            continue
        # Calcular parent
        parent = ".".join(leaf.split(".")[:-1])
        nodes.append({"id": leaf, "label": label, "parent": parent, "is_leaf": True})

    # Filtros sugeridos por hoja: heredan los que ya tiene fotoelectricos + algo especifico
    common_filters = ["principio_deteccion", "rango_mm", "salida_tipo", "conexion",
                      "ip_rating", "tipo_sensor", "material_carcasa"]
    leaf_filters = {leaf: common_filters for leaf in leaf_label_map}

    register_payload = {
        "nodes": nodes,
        "definitions": {},
        "leaf_filters": leaf_filters,
    }
    with open("sick_recat_register.json", "w", encoding="utf-8") as f:
        json.dump(register_payload, f, ensure_ascii=False)
    print(f"\nSaved sick_recat_register.json: {len(nodes)} nodos nuevos, "
          f"{len(leaf_filters)} hojas con filtros")

    # Productos batch
    import os
    os.makedirs("sick_recat_chunks", exist_ok=True)
    chunk_size = 500
    for i in range(0, len(new_assignments), chunk_size):
        chunk = new_assignments[i:i + chunk_size]
        cn = i // chunk_size + 1
        with open(f"sick_recat_chunks/chunk_{cn:02d}.json", "w", encoding="utf-8") as f:
            json.dump({"products": chunk}, f, ensure_ascii=False)
    print(f"  {(len(new_assignments) + chunk_size - 1) // chunk_size} chunks")


if __name__ == "__main__":
    main()
