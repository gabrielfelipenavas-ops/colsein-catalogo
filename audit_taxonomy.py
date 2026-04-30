"""Audita la taxonomia del catalogo: renombra labels confusos, fusiona
duplicados, reasigna productos huerfanos y borra categorias vacias.

Pasos:
  1. POST /api/admin/import-products-batch para mover productos de los
     nodos duplicados / huerfanos a sus destinos correctos.
  2. POST /api/admin/update-nodes con la lista de renames + cambio de is_leaf
     para el parent fotoelectricos.
  3. POST /api/admin/delete-nodes con los nodos a eliminar (duplicados ya
     vacios + categorias placeholder con 0 productos).

Requiere ADMIN_USER y ADMIN_PASS en el entorno (o en .env.local cargado
por el script que llama).
"""
import json
import os
import sys
import urllib.request
import urllib.error


BASE_URL = os.environ.get("COLSEIN_URL",
                          "https://web-production-f7337.up.railway.app").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER")
ADMIN_PASS = os.environ.get("ADMIN_PASS")


# ---------------------------------------------------------------------------
# 1. Renames de labels
# ---------------------------------------------------------------------------
# Estrategia: el "para que sirve" va primero; el codigo/serie del fabricante
# (W8, KT5, CAPAROC, etc.) va al final entre parentesis para quien lo conoce.
LABEL_RENAMES = {
    # === Fotocelulas SICK: codigos W/G se vuelven secundarios ===
    "deteccion-posicionamiento.fotoelectricos":
        "Otras fotocelulas (sin clasificar)",
    "deteccion-posicionamiento.fotoelectricos-w8":
        "Fotocelulas miniatura uso general (W8)",
    "deteccion-posicionamiento.fotoelectricos-w9":
        "Fotocelulas compactas robustas (W9)",
    "deteccion-posicionamiento.fotoelectricos-w11":
        "Fotocelulas de largo alcance (W11)",
    "deteccion-posicionamiento.fotoelectricos-w12":
        "Fotocelulas alta gama configurables (W12)",
    "deteccion-posicionamiento.fotoelectricos-w-grandes":
        "Fotocelulas industriales para grandes distancias (W18/W27/W280)",
    "deteccion-posicionamiento.fotoelectricos-w-pequenos":
        "Fotocelulas subminiatura para detalles (W2/W4)",
    "deteccion-posicionamiento.fotoelectricos-g6-compactos":
        "Fotocelulas compactas economicas (G6)",
    "deteccion-posicionamiento.fotoelectricos-g10":
        "Fotocelulas universales de alta deteccion (G10)",
    "deteccion-posicionamiento.fotoelectricos-cilindricos-m18":
        "Fotocelulas cilindricas roscadas M18",

    # === Otros sensores SICK: traducir codigo de serie ===
    "deteccion-posicionamiento.sensores-contraste":
        "Sensores de contraste para deteccion de marcas (KT)",
    "deteccion-posicionamiento.sensores-fibra":
        "Amplificadores con fibra optica (WF/WLL)",
    "deteccion-posicionamiento.sensores-luminiscencia":
        "Sensores de luminiscencia y fluorescencia (LUT)",
    "deteccion-posicionamiento.sensores-uv":
        "Sensores ultravioleta UV (UF)",
    "deteccion-posicionamiento.rejillas-fotoelectricas":
        "Rejillas / barreras fotoelectricas multihaz (ELG/MLG)",
    "deteccion-posicionamiento.cables-conexion":
        "Cables y conectores para sensores (DOL)",
    "deteccion-posicionamiento.lectores-codigo":
        "Lectores de codigo de barras y 2D",
    "deteccion-posicionamiento.sensores-distancia":
        "Sensores de distancia (laser / ultrasonico)",

    # === Borneras: descripcion clara antes de la jerga ===
    "borneras-y-conexion.borneras-pcb":
        "Borneras para circuito impreso (PCB)",
    "borneras-y-conexion.borneras-pcb-vertical":
        "Borneras para PCB en posicion vertical / angular",
    "borneras-y-conexion.borneras-tornillo":
        "Borneras para riel DIN, conexion a tornillo",
    "borneras-y-conexion.borneras-push-in":
        "Borneras para riel DIN, conexion rapida (push-in / resorte)",
    "borneras-y-conexion.borneras-rapidas":
        "Borneras de conexion rapida sin herramientas",
    "borneras-y-conexion.borneras-fusible":
        "Borneras con portafusible incorporado",
    "borneras-y-conexion.borneras-seccionables":
        "Borneras seccionables (de cuchilla)",
    "borneras-y-conexion.borneras-alta-corriente":
        "Borneras de potencia / alta corriente",

    # === Conectores ===
    "conectores-industriales.conectores-pcb":
        "Conectores enchufables para circuito impreso (PCB)",
    "conectores-industriales.conectores-pesados":
        "Conectores industriales pesados (heavy duty)",
    "conectores-industriales.conectores-fotovoltaicos":
        "Conectores para sistemas fotovoltaicos / paneles solares",
    "conectores-industriales.conectores-circulares-m8-m12":
        "Conectores circulares M8 / M12 para sensores",
    "conectores-industriales.conectores-circulares-m17-m58":
        "Conectores circulares grandes (M17 a M58)",
    "conectores-industriales.conectores-datos":
        "Conectores de datos / Ethernet industrial",

    # === Control / OPLC ===
    "control-automatizacion.oplc":
        "Controladores con HMI integrada (OPLC: PLC + pantalla)",
    "control-automatizacion.oplc.vision-unistream":
        "PLC + HMI Vision / UniStream (Unitronics)",
    "control-automatizacion.oplc.jazz-samba":
        "PLC + HMI compactos Jazz / Samba (Unitronics)",
    "control-automatizacion.io-remoto":
        "Modulos de I/O remoto",
    "control-automatizacion.plc-modular":
        "PLC modular",

    # === Fuentes / energia ===
    "fuentes-alimentacion.fuentes-dc-industriales":
        "Fuentes DC industriales para riel DIN",
    "fuentes-alimentacion.convertidores-dc-dc":
        "Convertidores DC/DC",
    "fuentes-alimentacion.ups-respaldo":
        "UPS y energia de respaldo",
    "energia-infraestructura-electrica.fuentes-dc":
        "Fuentes DC industriales",
    "energia-infraestructura-electrica.spd":
        "Proteccion contra sobretensiones (SPD)",
    "energia-infraestructura-electrica.ups-redundancia":
        "UPS y modulos de redundancia",
    "energia-infraestructura-electrica.interfaces-rele":
        "Interfaces de rele (acoplamiento E/S)",
    "energia-infraestructura-electrica.bornes":
        "Bornes generales",

    # === Acondicionamiento / aisladores ===
    "acondicionamiento-de-senal.aisladores":
        "Aisladores y convertidores de senal",

    # === Seguridad ===
    "seguridad-maquina-industrial.cortinas-luz":
        "Cortinas y barreras de luz de seguridad",
    "seguridad-maquina-industrial.paneles-malla":
        "Vallas de malla / paneles de proteccion perimetral",
    "seguridad-maquina-industrial.escaner-laser-seguridad":
        "Escaneres laser de seguridad",
    "seguridad-maquina-industrial.interruptores-seguridad":
        "Interruptores de seguridad",
    "seguridad-maquina-industrial.controladores-seguridad":
        "Controladores de seguridad programables",
    "seguridad-maquina-industrial.guard-locking":
        "Cerraduras de seguridad (guard locking)",
    "seguridad-maquina-industrial.trapped-key":
        "Sistemas de llave atrapada (trapped key)",

    # === Reles ===
    "reles-y-contactores.reles-acoplamiento":
        "Reles de interfaz / acoplamiento E/S",
    "reles-y-contactores.reles-seguridad":
        "Reles de seguridad",
    "reles-y-contactores.contactores":
        "Contactores y aparatos de conmutacion",
    "reles-y-contactores.modulos-logicos":
        "Modulos logicos / temporizadores",

    # === Proteccion ===
    "proteccion-circuitos.disyuntores-electronicos":
        "Disyuntores electronicos inteligentes (CAPAROC)",
    "proteccion-circuitos.dps-sobretension":
        "Proteccion contra sobretensiones (DPS / SPD)",
    "proteccion-circuitos.guardamotores":
        "Guardamotores (disyuntores para motor)",
    "proteccion-circuitos.magnetotermicos":
        "Interruptores magnetotermicos (MCB)",

    # === Comunicacion / redes ===
    "comunicacion-industrial.switches-ethernet":
        "Switches Ethernet industrial",
    "comunicacion-industrial.pasarelas-convertidores":
        "Pasarelas y convertidores de protocolo",
    "comunicacion-industrial.seguridad-red":
        "Seguridad de red industrial / firewalls",
    "comunicacion-industrial.wireless":
        "Comunicacion wireless industrial",
    "comunicacion-industrial.fieldbus":
        "Buses de campo / fieldbus",
    "redes-comunicaciones-industriales.switches":
        "Switches de red",
    "redes-comunicaciones-industriales.routers":
        "Routers y firewalls",
    "redes-comunicaciones-industriales.fibra-conversores":
        "Conversores de fibra optica",
    "redes-comunicaciones-industriales.gateways-protocolo":
        "Gateways de protocolo",
    "redes-comunicaciones-industriales.bus-campo":
        "Buses de campo",

    # === HMI ===
    "hmi-visualizacion.hmi-fisica":
        "HMI / pantallas tactiles industriales",
    "hmi-visualizacion.hmi-ex":
        "HMI para zonas Ex (atmosferas explosivas)",

    # === Marcaje ===
    "marcaje-e-identificacion.impresoras-industriales":
        "Impresoras de etiquetas y marcaje industrial",
    "marcaje-e-identificacion.marcadores-cables":
        "Marcadores y rotuladores para cables",
    "marcaje-e-identificacion.sistemas-marcaje":
        "Sistemas y software de marcaje",

    # === Cables y distribucion ===
    "cables-y-distribucion.bloques-distribuidores":
        "Bloques distribuidores de potencia",
    "cables-y-distribucion.sistemas-cableado":
        "Sistemas de cableado prefabricado",
    "cables-y-distribucion.cables-sensor-actuador":
        "Cables para sensores y actuadores",
    "cables-conexion.cables.control-poder":
        "Cables de control y poder",
    "cables-conexion.cables.datos-bus":
        "Cables de datos / bus",
    "cables-conexion.cables.especiales":
        "Cables especiales",
    "cables-conexion.cables.fibra-optica":
        "Cables de fibra optica",
    "cables-conexion.cables.instrumentacion":
        "Cables de instrumentacion",

    # === Herramientas ===
    "herramientas-industriales.crimpadoras":
        "Crimpadoras y herramientas para cables",
    "herramientas-industriales.varios":
        "Otras herramientas industriales",

    # === Monitoreo de energia ===
    "monitoreo-de-energia.medidores":
        "Medidores y analizadores de energia",

    # === Motores ===
    "motores-movimiento.motores":
        "Motores electricos",
    "motores-movimiento.variadores":
        "Variadores de frecuencia (VFD)",
    "motores-movimiento.soft-starters":
        "Arrancadores suaves (soft starters)",
    "motores-movimiento.contactores-arrancadores":
        "Contactores y arrancadores para motor",
    "motores-movimiento.generadores":
        "Generadores",

    # === Computo industrial ===
    "computo-industrial.ipc-rack":
        "PCs industriales formato rack (IPC)",
    "computo-industrial.panel-pc":
        "Panel PC (PC con pantalla integrada)",
    "computo-industrial.embedded-box":
        "PCs embebidos compactos (box PC)",
    "computo-industrial.iot-gateways":
        "Gateways IoT industriales",
    "computo-industrial.daq-hardware":
        "Hardware de adquisicion de datos (DAQ)",

    # === Ex ===
    "equipos-zonas-ex.cajas-envolventes-ex":
        "Cajas y envolventes para zonas Ex",
    "equipos-zonas-ex.luminarias-ex":
        "Luminarias para zonas Ex",
    "equipos-zonas-ex.instrumentacion-ex":
        "Instrumentacion para zonas Ex",
    "equipos-zonas-ex.hmi-paneles-ex":
        "HMI y paneles para zonas Ex",
    "equipos-zonas-ex.sistemas-control-ex":
        "Sistemas de control para zonas Ex",

    # === Iluminacion ===
    "iluminacion-industrial.lamparas-led":
        "Luminarias LED industriales",

    # === Mecanica ===
    "mecanica-estructura.perfiles":
        "Perfiles estructurales de aluminio",
    "mecanica-estructura.mesas-estaciones":
        "Mesas y estaciones de trabajo",
    "mecanica-estructura.conectores":
        "Conectores y herrajes mecanicos",

    # === Software ===
    "software-industrial.scada-hmi":
        "Software SCADA / HMI",
    "software-industrial.historian":
        "Software historian (registro historico)",
    "software-industrial.mes-batch":
        "Software MES / Batch",
    "software-industrial.engineering-design":
        "Software de ingenieria y diseno",
    "software-industrial.test-analysis":
        "Software de pruebas y analisis",
    "software-industrial.energy-management":
        "Software de gestion de energia",
    "software-industrial.cloud-data-hub":
        "Cloud / data hub industrial",
    "software-industrial.operations-mobile":
        "Software de operaciones moviles",
}


# ---------------------------------------------------------------------------
# 2. Reasignar productos: duplicados + huerfanos
# ---------------------------------------------------------------------------
# leaf actual -> leaf destino. Solo aplicara a productos que estan ahi hoy.
PRODUCT_REASSIGNMENTS = {
    # Duplicados: el ID corto (sensor-X) y el largo conviven; conservamos
    # el largo "sensores-X" porque es mas explicito.
    "deteccion-posicionamiento.inductivos":  "deteccion-posicionamiento.sensores-inductivos",
    "deteccion-posicionamiento.capacitivos": "deteccion-posicionamiento.sensores-capacitivos",
}

# Los 237 productos del parent 'fotoelectricos' (no leaf) se quedan ahi:
# vamos a marcar ese parent como leaf con label "Otras fotocelulas" para
# que sean visibles. No los movemos.


# ---------------------------------------------------------------------------
# 3. Borrar nodos vacios / placeholder y los duplicados ya vaciados
# ---------------------------------------------------------------------------
NODES_TO_DELETE = [
    # Duplicados que ya quedaron vacios despues del paso 2
    "deteccion-posicionamiento.inductivos",
    "deteccion-posicionamiento.capacitivos",
]


# ---------------------------------------------------------------------------
# 4. Marcar nodos como leaf (el parent fotoelectricos tiene productos)
# ---------------------------------------------------------------------------
LEAF_TOGGLES = {
    "deteccion-posicionamiento.fotoelectricos": True,
}


# ---------------------------------------------------------------------------
# Helpers HTTP
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
        sys.exit(f"Login fallo: {code} {body}")
    return body["token"]


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"[1/4] Descargando productos de {BASE_URL} ...")
    prods = json.loads(urllib.request.urlopen(
        BASE_URL + "/api/products", timeout=60).read())
    print(f"      {len(prods)} productos en total")

    # Reasignaciones: armar payload
    moves = []
    for p in prods:
        leaf = p.get("leaf") or ""
        if leaf in PRODUCT_REASSIGNMENTS:
            new_leaf = PRODUCT_REASSIGNMENTS[leaf]
            cp = {
                "id": p["id"],
                "brand": p.get("brand"),
                "model": p.get("model"),
                "name": p.get("name"),
                "family": p.get("family"),
                "leaf": new_leaf,
                "secondary_leaves": p.get("secondary_leaves") or [],
                "desc": p.get("description") or p.get("desc"),
                "url": p.get("manufacturer_url") or p.get("url"),
                "lifecycle": p.get("lifecycle") or "active",
                "is_software": p.get("is_software", 0),
            }
            for k, v in (p.get("attributes") or {}).items():
                cp.setdefault(k, v)
            moves.append((p["id"], leaf, new_leaf, cp))

    print(f"      {len(moves)} productos a reasignar (duplicados):")
    by_route = {}
    for pid, src, dst, _ in moves:
        by_route[(src, dst)] = by_route.get((src, dst), 0) + 1
    for (src, dst), n in by_route.items():
        print(f"        {n:4d}  {src}  ->  {dst}")

    print(f"\n[2/4] {len(LABEL_RENAMES)} renames de labels listos")
    print(f"[3/4] {len(LEAF_TOGGLES)} cambios de is_leaf")
    print(f"[4/4] {len(NODES_TO_DELETE)} nodos a eliminar tras vaciado")

    if dry_run:
        print("\n[dry-run] No se envia nada.")
        return

    token = admin_login()
    headers = {"X-Admin-Token": token}

    # Paso 1: mover productos para vaciar duplicados
    if moves:
        chunk_size = 500
        payload = [m[3] for m in moves]
        print(f"\n>>> Subiendo {len(payload)} reasignaciones en chunks de {chunk_size} ...")
        for i in range(0, len(payload), chunk_size):
            chunk = payload[i:i + chunk_size]
            code, body = http_post("/api/admin/import-products-batch",
                                   {"products": chunk}, headers)
            if code != 200:
                sys.exit(f"chunk {i} fallo: {code} {body}")
            print(f"    chunk {i // chunk_size + 1}: "
                  f"+{body.get('inserted', 0)} ins, "
                  f"+{body.get('updated', 0)} upd, "
                  f"{body.get('skipped', 0)} skp")

    # Paso 2: renames + leaf toggles
    updates = []
    for nid, label in LABEL_RENAMES.items():
        upd = {"id": nid, "label": label}
        if nid in LEAF_TOGGLES:
            upd["is_leaf"] = LEAF_TOGGLES[nid]
        updates.append(upd)
    # Anadir leaf toggles que no esten en LABEL_RENAMES
    for nid, is_leaf in LEAF_TOGGLES.items():
        if nid not in LABEL_RENAMES:
            updates.append({"id": nid, "is_leaf": is_leaf})

    print(f"\n>>> Aplicando {len(updates)} renames/toggles ...")
    code, body = http_post("/api/admin/update-nodes",
                           {"updates": updates}, headers)
    if code != 200:
        sys.exit(f"update-nodes fallo: {code} {body}")
    print(f"    {body.get('updated')} nodos actualizados, "
          f"{len(body.get('unknown_ids', []))} ids desconocidos")
    if body.get("unknown_ids"):
        print(f"    desconocidos: {body['unknown_ids']}")

    # Paso 3: borrar nodos
    if NODES_TO_DELETE:
        print(f"\n>>> Borrando {len(NODES_TO_DELETE)} nodos ...")
        code, body = http_post("/api/admin/delete-nodes",
                               {"node_ids": NODES_TO_DELETE}, headers)
        if code != 200:
            sys.exit(f"delete-nodes fallo: {code} {body}")
        print(f"    borrados: {body.get('removed_count')}, "
              f"huerfanos: {body.get('orphan_products')}")

    print("\nLISTO.")


if __name__ == "__main__":
    main()
