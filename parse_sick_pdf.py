"""Parsea el catalogo SICK PDF (sick_pdf_text.json) y extrae productos.

Patrón: cada variante de producto aparece en una tabla con
   TYPE-CODE  7-DIGIT-REFERENCE
donde TYPE-CODE es el modelo (e.g. GTE6-P1212, IME08-02BNSZT0S, S32B-2011BA)
y la referencia (e.g. 1051783) es el SKU oficial SICK.
"""
import json
import re
from collections import defaultdict


# Mapeo de secciones del catalogo a hojas de la taxonomia interna.
# Cada seccion tiene: code letter, family hint, leaf id.
# Las paginas estan organizadas por secciones segun el TOC de la pag 2.
SECTION_TO_LEAF = {
    # Section letter (or family keyword) -> leaf id
    "fotocelulas": "deteccion-posicionamiento.fotoelectricos",
    "fotocélulas": "deteccion-posicionamiento.fotoelectricos",
    "fotoeléctricas": "deteccion-posicionamiento.fotoelectricos",
    "fotoelectricas": "deteccion-posicionamiento.fotoelectricos",
    "rejillas": "deteccion-posicionamiento.fotoelectricos",  # rejillas fotoeléctricas (no safety)
    "proximidad inductivos": "deteccion-posicionamiento.sensores-inductivos",
    "proximidad capacitivos": "deteccion-posicionamiento.sensores-capacitivos",
    "sensores magneticos": "deteccion-posicionamiento.sensores-magneticos",
    "magnéticos para cilindros": "deteccion-posicionamiento.sensores-magneticos",
    "identificacion": "deteccion-posicionamiento.lectores-codigo",
    "identificación": "deteccion-posicionamiento.lectores-codigo",
    "escáneres de códigos": "deteccion-posicionamiento.lectores-codigo",
    "escaneres de codigos": "deteccion-posicionamiento.lectores-codigo",
    "lector": "deteccion-posicionamiento.lectores-codigo",
    "fluidos": "instrumentacion-medicion.flujo",
    "registro": "deteccion-posicionamiento.fotoelectricos",  # contraste, color (reuse)
    "distancia": "deteccion-posicionamiento.sensores-distancia",
    "vision": "deteccion-posicionamiento.vision",
    "visión": "deteccion-posicionamiento.vision",
    "inspector": "deteccion-posicionamiento.vision",
    "protección optoelectrónicos": "seguridad-maquina-industrial.cortinas-luz",
    "proteccion optoelectronicos": "seguridad-maquina-industrial.cortinas-luz",
    "escáneres láser de seguridad": "seguridad-maquina-industrial.escaner-laser-seguridad",
    "escaneres laser de seguridad": "seguridad-maquina-industrial.escaner-laser-seguridad",
    "interruptores de seguridad": "seguridad-maquina-industrial.interruptores-seguridad",
    "control de seguridad": "seguridad-maquina-industrial.controladores-seguridad",
    "encoder": "deteccion-posicionamiento.encoders.incrementales",  # default; absolute heuristics later
}


def detect_leaf(family_text):
    """Heurística para mapear el nombre de familia al leaf interno."""
    t = (family_text or "").lower()
    # Heurísticas en orden de prioridad
    if "lidar" in t or "lms" in t:
        return "deteccion-posicionamiento.lidar-2d"
    if "encoder" in t and "absolut" in t:
        return "deteccion-posicionamiento.encoders.absolutos"
    if "encoder" in t:
        return "deteccion-posicionamiento.encoders.incrementales"
    if "escáner láser de seguridad" in t or "escaner laser de seguridad" in t or "s300" in t or "s3000" in t:
        return "seguridad-maquina-industrial.escaner-laser-seguridad"
    if "cortinas" in t or "miniTwin" in t or "deTec" in t.lower() or "m4000" in t or ("protección" in t and "optoelectró" in t):
        return "seguridad-maquina-industrial.cortinas-luz"
    if "interruptor" in t and "segur" in t:
        return "seguridad-maquina-industrial.interruptores-seguridad"
    if "flexi soft" in t or "speed monitor" in t or "standstill" in t or "ue10" in t or "ue23" in t or "ue48" in t:
        return "seguridad-maquina-industrial.controladores-seguridad"
    if "rejilla" in t:
        return "deteccion-posicionamiento.fotoelectricos"
    if "fotocelula" in t or "fotocélula" in t or "fotoeléctric" in t or "fotoelectric" in t:
        return "deteccion-posicionamiento.fotoelectricos"
    if "inductiv" in t:
        return "deteccion-posicionamiento.sensores-inductivos"
    if "capacitiv" in t:
        return "deteccion-posicionamiento.sensores-capacitivos"
    if "magnétic" in t or "magnetic" in t:
        return "deteccion-posicionamiento.sensores-magneticos"
    if "código" in t or "codigo" in t or "barcode" in t or "lector" in t or "clv" in t.lower():
        return "deteccion-posicionamiento.lectores-codigo"
    if "fluido" in t or "lfp" in t.lower() or "lfv" in t.lower() or "presión" in t:
        return "instrumentacion-medicion.flujo"
    if "registro" in t and "contraste" not in t:
        return "deteccion-posicionamiento.fotoelectricos"
    if "distancia" in t or "ultras" in t:
        return "deteccion-posicionamiento.sensores-distancia"
    if "visión" in t or "vision" in t or "inspector" in t:
        return "deteccion-posicionamiento.vision"
    return None


def parse_sick_pdf(input_json="sick_pdf_text.json"):
    pages = json.load(open(input_json, encoding="utf-8"))
    products = []
    seen_refs = set()

    # Track current section/family by scanning for big headers
    current_family = None
    current_section_letter = None
    current_subtype = None  # captures titles like "GTE6", "IME08" inside a section

    # Pattern for product variants: TYPE-CODE  REFERENCE(7 digitos)
    # Type-code: at least 4 chars, comienza con letra mayuscula, puede tener letras/digitos/guiones/puntos
    variant_re = re.compile(r"\b([A-Z][A-Z0-9](?:[A-Z0-9.\-/]{2,30}))\s+(\d{7})\b")

    # Pattern for family/subsection title: things like
    # "G6 FOTOCÉLULAS COMPACTAS"  or  "IM Standard SENSORES DE PROXIMIDAD INDUCTIVOS"
    section_title_re = re.compile(r"^\s*([A-Z][A-Za-z0-9 ]+?)\s+([A-ZÁÉÍÓÚÑ]{4,}(?:\s+[A-ZÁÉÍÓÚÑa-z\(\)]+){1,8})\s*$")

    for p in pages:
        page_num = p["page"]
        text = p["text"]
        lines = text.split("\n")

        # 1) Detect family from page header (first ~15 lines)
        for line in lines[:18]:
            line = line.strip()
            # Ignore obvious noise
            if not line or "SICK C ATÁLOGO" in line or "Sujeto a" in line:
                continue
            # All-caps short title ("FOTOCÉLULAS COMPACTAS", "SENSORES DE PROXIMIDAD INDUCTIVOS")
            if line.isupper() and 8 < len(line) < 80 and not any(c.isdigit() for c in line):
                if not any(skip in line.lower() for skip in ["catálogo", "sick", "página", "pagina", "información"]):
                    current_family = line.title()
                    break

        # 2) Find variants on the page
        for m in variant_re.finditer(text):
            type_code, ref = m.group(1), m.group(2)
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            # Filtros heurísticos: descartar matches falsos
            if len(type_code) < 4:
                continue
            # Falsos positivos comunes: nombres de archivo, docs, codigos genericos
            if type_code.startswith(("HTTP", "WWW", "DIN", "ISO", "EN", "PDF", "ASCII", "CAD", "BEF", "KTM", "CSM")):
                continue
            # SKUs SICK reales suelen tener al menos un guion o numero+letra mezclado
            if not (("-" in type_code) or any(c.isdigit() for c in type_code)):
                continue
            # Descartar codigos sospechosamente cortos sin estructura SICK
            if len(type_code) < 5 and "-" not in type_code:
                continue

            # Derivar leaf desde la familia detectada
            leaf = detect_leaf(current_family or "")

            # Captura de specs cercanos (10 lineas antes)
            mstart = m.start()
            chunk_start = max(0, mstart - 600)
            chunk = text[chunk_start:mstart + 200]

            # Extract specs heuristics from chunk
            attrs = {}
            # Switch distance "Sn" / "Distancia de conmutación"
            md = re.search(r"(\d+(?:[\.,]\d+)?)\s*mm\b", chunk)
            if md and ("conmutación" in chunk.lower() or "distancia" in chunk.lower() or "sn" in chunk.lower()):
                try:
                    attrs["rango_mm"] = float(md.group(1).replace(",", "."))
                except: pass
            # Output type — detectado del SKU (más confiable que del chunk)
            # SICK convención: dash-P o dash-N o BPS/BNS dentro del SKU
            sku_upper = type_code.upper()
            mout = re.search(r"-([PN])\d", sku_upper) or re.search(r"\bB([PN])S", sku_upper)
            if mout:
                attrs["salida_tipo"] = "pnp" if mout.group(1) == "P" else "npn"
            elif re.search(r"\bDC\s*de\s*2\s*hilos", chunk, re.I) or "BD" in sku_upper:
                attrs["salida_tipo"] = "dc-2-hilos"
            # Connection
            if re.search(r"\bM8\b", chunk) and "conector" in chunk.lower():
                attrs["conexion"] = "m8"
            elif re.search(r"\bM12\b", chunk) and "conector" in chunk.lower():
                attrs["conexion"] = "m12"
            elif "cable" in chunk.lower():
                attrs["conexion"] = "cable"
            # Tamano metric
            mt = re.search(r"\bM\s*(\d{1,2})\s*x", chunk)
            if mt: attrs["tamano_metric"] = f"M{mt.group(1)}"
            # IP
            mip = re.search(r"IP\s*(\d{2}(?:\s*/\s*\d+\s*[Kk]?)?)", chunk)
            if mip: attrs["ip_rating"] = "IP" + mip.group(1).replace(" ", "")
            # Detection principle (from section)
            if current_family:
                tl = current_family.lower()
                if "fotocelula" in tl or "fotocélula" in tl:
                    if "supresión del fondo" in chunk.lower() or "background suppression" in chunk.lower():
                        attrs["principio_deteccion"] = "photoelectric_diffuse_bgs"
                    elif "barrera" in chunk.lower() or "thru-beam" in chunk.lower():
                        attrs["principio_deteccion"] = "photoelectric_thru_beam"
                    elif "retror" in chunk.lower():
                        attrs["principio_deteccion"] = "photoelectric_retro"
                    else:
                        attrs["principio_deteccion"] = "photoelectric_diffuse"
            # Type sensor
            if leaf and "inductivos" in leaf:
                attrs["tipo_sensor"] = "inductivo"
            elif leaf and "capacitivos" in leaf:
                attrs["tipo_sensor"] = "capacitivo"
            elif leaf and "fotoelectricos" in leaf:
                attrs["tipo_sensor"] = "fotoelectrico"

            products.append({
                "id": f"scraped-sick-{ref}",
                "brand": "sick",
                "model": type_code,
                "name": f"SICK {type_code}",
                "family": current_family or "Sensor SICK",
                "leaf": leaf or "deteccion-posicionamiento.fotoelectricos",
                "secondary_leaves": [],
                "desc": f"Ref. {ref}. {current_family or ''}",
                "url": f"https://www.sick.com/es/es/p/p{ref}",
                "image_url": None,
                "lifecycle": "active",
                "is_software": 0,
                "datasheet_url": f"https://cdn.sick.com/media/pdf/{ref}.pdf",
                "_page": page_num,  # solo para join con imagenes; no se serializa al server
                **attrs,
            })

    # Resumen
    by_leaf = defaultdict(int)
    for p in products:
        by_leaf[p["leaf"]] += 1
    return products, dict(by_leaf)


if __name__ == "__main__":
    products, by_leaf = parse_sick_pdf()
    print(f"Total productos extraidos: {len(products)}")
    print()
    print("Por leaf:")
    for l, n in sorted(by_leaf.items(), key=lambda kv: -kv[1]):
        print(f"  {l}: {n}")
    # Save
    with open("sick_products.json", "w", encoding="utf-8") as f:
        json.dump({"products": products}, f, ensure_ascii=False)
    print()
    print("Guardado en sick_products.json")
    print()
    print("=== Sample ===")
    for p in products[:5]:
        print(p)
