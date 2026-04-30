"""Parsea los 59 PDFs Phoenix Contact (texto extraido en phoenix_pdf_texts.json).

Patrón: igual que SICK — Type + 7-digit Order No.
Mapeo cada PDF a un leaf especifico bajo el trunk 'phoenix-contact'.
"""
import json
import re
from collections import defaultdict


# Mapeo de PDF filename pattern -> (leaf_id, leaf_label, family_label, is_product_catalog)
# Si is_product_catalog=False, lo descartamos (brochures, info técnica).
PDF_MAPPING = {
    # Sales Guides (catálogos de productos) - alta prioridad
    "1357929_EN_SG_Reihenklemmen": ("phoenix-contact.terminales", "Terminales / Bornas", "Reihenklemmen / Terminales", True),
    "1357912_EN_SG_Verteilerbloecke": ("phoenix-contact.distribuidores", "Bloques de distribución", "Verteilerblöcke", True),
    "1357900_EN_SG_Tools": ("phoenix-contact.herramientas", "Herramientas", "Tools", True),
    "1345531_EN_SG_Installationssyt": ("phoenix-contact.instalacion", "Sistemas de instalación", "Installation Systems", True),
    "1345979_EN_SG_UESS_und_Entstoe": ("phoenix-contact.proteccion-sobretension", "Protección sobretensión", "UESS / Surge Protection", True),
    "1364515_ES_SG_Fame": ("phoenix-contact.marcaje-cables", "Marcaje cables", "FAME / Marking", True),
    "1429216_EN_SG_Rangierverteiler": ("phoenix-contact.distribuidores-cableado", "Distribuidores cableado", "Rangierverteiler", True),
    "1437076_EN_SG_Energiemonitorin": ("phoenix-contact.monitoreo-energia", "Monitoreo de energía", "Energy Monitoring", True),
    "1439790_EN_SG_Relais-und_Logik": ("phoenix-contact.reles-logica", "Relés y módulos lógicos", "Relais & Logik", True),
    "1440387_ES_SG_Geraeteschutzsch": ("phoenix-contact.guardamotores", "Guardamotores / disyuntores", "Geräteschutzschalter", True),
    "1440406_ES_SG_Signalaufbereitu": ("phoenix-contact.acondicionamiento-senal", "Acondicionamiento de señal", "Signalaufbereitung", True),
    "1440441_ES_SG_Schaltgeraete_Mo": ("phoenix-contact.aparatos-conmutacion", "Aparatos de conmutación", "Schaltgeräte", True),
    "1443524_ES_SG_Systemverkabelun": ("phoenix-contact.cableado-sistema", "Cableado de sistema", "Systemverkabelung", True),
    "1443634_ES_SG_Schwere_Steckver": ("phoenix-contact.conectores-pesados", "Conectores industriales pesados", "Schwere Steckverbinder", True),
    "1443689_EN_SG_Printer_und_Mark": ("phoenix-contact.impresoras-marcaje", "Impresoras y sistemas de marcaje", "Printer & Marking", True),
    "1665629_ES_SG_Remote_IO-System": ("phoenix-contact.io-remoto", "Sistemas E/S remotas", "Remote IO", True),
    "1756224_EN_SG_Industrial_Wireless": ("phoenix-contact.wireless-industrial", "Wireless industrial", "Industrial Wireless", True),
    "1817841_EN_SG_Beleuchtung_und_": ("phoenix-contact.iluminacion", "Iluminación industrial", "Beleuchtung", True),
    "1314669_EN_SG_Power_Supplies": ("phoenix-contact.fuentes-alimentacion", "Fuentes de alimentación", "Power Supplies", True),
    # Catálogos especificos (no SG pero tienen productos)
    "CAT_8_2026_ES_LoRes": ("phoenix-contact.catalogo-general", "Catálogo general 2026", "Phoenix Contact 2026", True),
    "1907583_ES_Leiterplatten-Steck": ("phoenix-contact.conectores-pcb", "Conectores PCB", "Leiterplatten-Steckverbinder", True),
    "1907695_ES_M17-M58_LoRes": ("phoenix-contact.conectores-circulares", "Conectores circulares M17-M58", "M17-M58", True),
    "52003573_ES_M5-M12_LoRes": ("phoenix-contact.conectores-circulares-m12", "Conectores circulares M5-M12", "M5-M12", True),
    "52000302_ES_PV-Steckverbinder": ("phoenix-contact.conectores-fotovoltaicos", "Conectores fotovoltaicos PV", "PV Steckverbinder", True),
    "52005722_ES_Datensteckverbin": ("phoenix-contact.conectores-datos", "Conectores de datos", "Datensteckverbinder", True),
    "52003209_EN_Industrial_Ethernet": ("phoenix-contact.ethernet-industrial", "Ethernet industrial", "Industrial Ethernet", True),
    "52003261_ES_Industrial_Etherne": ("phoenix-contact.ethernet-industrial", "Ethernet industrial", "Industrial Ethernet", True),
    "52007281_EN_Feldbus_Netzwerke": ("phoenix-contact.fieldbus", "Redes Fieldbus", "Feldbus Netzwerke", True),
    "5149416_EN_Explosionsschutz": ("phoenix-contact.proteccion-explosion", "Protección zonas Ex", "Explosionsschutz", True),
    "5177475_ES_CLIPLINE_Quality": ("phoenix-contact.terminales-clipline", "CLIPLINE Quality", "CLIPLINE", True),
    "1455158_ES_Seitliche_Federkraftklemmen": ("phoenix-contact.bornas-resorte-lateral", "Bornas resorte lateral", "Federkraftklemmen", True),
    "1322147_ES_CAPAROC": ("phoenix-contact.proteccion-circuito-caparoc", "Protección de circuitos CAPAROC", "CAPAROC", True),
    "1153740_ES_HMI_IPC_Operation_M": ("phoenix-contact.hmi-ipc", "HMI / IPC", "HMI IPC", True),
    "1237616_EN_CLIXTAB": ("phoenix-contact.clixtab", "CLIXTAB conector rápido", "CLIXTAB", True),
    "1500730_ES_THERMOMARK_E-SERIES": ("phoenix-contact.impresoras-thermomark", "Impresoras THERMOMARK", "THERMOMARK E-Series", True),
    "1691289_EN_THERMOMARK_PRIME_2_0": ("phoenix-contact.impresoras-thermomark", "Impresoras THERMOMARK", "THERMOMARK PRIME 2.0", True),
    "1693496_EN_THERMOMARK_E_300_DOUBLE": ("phoenix-contact.impresoras-thermomark", "Impresoras THERMOMARK", "THERMOMARK E300 DOUBLE", True),
    "52004159_ES_Marking_system": ("phoenix-contact.marcaje", "Sistemas de marcaje", "Marking System", True),
    "52007942_ES_Mobile_Printing": ("phoenix-contact.impresion-movil", "Impresión móvil", "Mobile Printing", True),
    "1195140_EN_NSE": ("phoenix-contact.nse", "NSE / Network Sicherheit", "NSE", True),
    "1197991_ES_Produktuebersicht_P": ("phoenix-contact.catalogo-general", "Catálogo general", "Produktübersicht", True),
    # Brochures / info / tecnicos (DESCARTAR)
    "1093964_EN_HQ_Tunneltechnologie_Image": (None, None, None, False),
    "1110045_ES_INT_Security": (None, None, None, False),
    "1025867_ES_INT_SKEDD": (None, None, None, False),
    "1188791_EN_Schirmung": (None, None, None, False),
    "1333069_ES_Single_Pair_Etherne": (None, None, None, False),
    "1334671_ES_Energies_Battery": (None, None, None, False),
    "1449251_ES_Markteinfuehrung_Fi": (None, None, None, False),
    "1462232_ES_Markteinfuehrung_FL": (None, None, None, False),
    "1549317_ES_Power_Reliability": (None, None, None, False),
    "ES_PLCnext_Technology": (None, None, None, False),
    "52007341_ES_Funktionale_Sicher": (None, None, None, False),
    "52003540_EN_HQ_Circuit_Breaker": (None, None, None, False),
    "52007057_EN_MSR-Anwenderhandbuch": (None, None, None, False),
    "1030776_EN_Industrielle_Fernkommunikation": (None, None, None, False),
    "00140472_PDF_LORES": (None, None, None, False),
    "00140512_PDF_LORES": (None, None, None, False),
    "phoenix-contact-1760157-es": (None, None, None, False),
}


def get_mapping(filename):
    """Busca la entrada de mapping cuyo prefix matchee el filename."""
    base = filename.replace(".pdf", "").replace(" (1)", "")
    for prefix, info in PDF_MAPPING.items():
        if base.startswith(prefix):
            return info
    return (None, None, None, False)


def parse_one_pdf(filename, pdf_data, mapping):
    """Extrae productos de un PDF dado su texto pre-extraido."""
    leaf_id, leaf_label, family_label, is_catalog = mapping
    if not is_catalog:
        return [], 0
    pages = pdf_data["pages"]
    products = []
    seen_refs = set()
    # Pattern: Type code + 7-digit order number
    # El Type Phoenix puede tener espacios, comas, slashes, guiones, paréntesis.
    # Ej: "SMKDSN 1,5/ 2-5,08", "QUINT4-PS/1AC/24DC/10", "UT 4-D"
    variant_re = re.compile(
        r"\b([A-Z][A-Z0-9](?:[A-Z0-9 .,\-/+()]{2,60}[A-Z0-9)])?)\s+(\d{7})\b"
    )

    for p in pages:
        text = p["text"]
        page_num = p["page"]
        for m in variant_re.finditer(text):
            type_code = m.group(1).strip()
            ref = m.group(2)
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            # Filtros heurísticos
            if len(type_code) < 3:
                continue
            # Descartar palabras comunes que matchean el patrón pero no son SKUs
            type_upper = type_code.upper()
            if type_upper.startswith((
                "PHOENIX", "CONTACT", "WWW", "HTTP", "PDF", "ISO", "DIN",
                "PAGE", "PAGINA", "PÁGINA", "SECTION", "CHAPTER",
                "ORDER", "PEDIDO", "VOLUMEN", "EMBALAJE",
                "SECTION", "FIG", "TABLE", "EJEMPLO", "EXAMPLE",
                "NOTE", "NOTA", "REF", "VERSION", "EDITION", "LORES",
            )):
                continue
            # Phoenix SKUs reales casi siempre tienen alguna mezcla de letra+digito
            # o un caracter especial (espacio, slash, guion)
            if not any(c.isdigit() for c in type_code) and len(type_code) < 4:
                continue
            if " " not in type_code and "-" not in type_code and "/" not in type_code and len(type_code) < 5:
                continue

            # Extraer atributos del contexto (300 chars antes)
            mstart = m.start()
            chunk = text[max(0, mstart - 600):mstart + 200]
            attrs = {}
            # Voltage
            mv = re.search(r"\b(\d{2,3}(?:[\.,]\d+)?)\s*V\s*DC\b", chunk, re.I)
            if mv:
                attrs["voltaje_dc"] = mv.group(1).replace(",", ".") + "VDC"
            mv = re.search(r"\b(\d{2,3}(?:[\.,]\d+)?)\s*V\s*AC\b", chunk, re.I)
            if mv:
                attrs["voltaje_ac"] = mv.group(1).replace(",", ".") + "VAC"
            # Current
            ma = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*A\b(?!.*[A-Z])", chunk)
            if ma:
                try: attrs["corriente_a"] = float(ma.group(1).replace(",", "."))
                except: pass
            # Section AWG
            mawg = re.search(r"\b(\d{1,2})\s*AWG\b", chunk, re.I)
            if mawg: attrs["calibre_awg"] = int(mawg.group(1))
            # Cross section mm²
            msec = re.search(r"(\d+(?:[\.,]\d+)?)\s*mm\s*[²2]", chunk)
            if msec:
                try: attrs["seccion_mm2"] = float(msec.group(1).replace(",", "."))
                except: pass
            # Poles (from "polos: N" or column 1 in table)
            mp = re.search(r"\b(\d+)\s*polos\b", chunk, re.I) or re.search(r"polos\s*[:=]\s*(\d+)", chunk, re.I)
            if mp:
                try: attrs["polos_interruptor"] = int(mp.group(1))
                except: pass
            # IP rating
            mip = re.search(r"IP\s*(\d{2}(?:\s*/\s*\d+\s*[Kk]?)?)", chunk, re.I)
            if mip: attrs["ip_rating"] = "IP" + mip.group(1).replace(" ", "")
            # Apantallado / shielded
            if re.search(r"\bapantallad", chunk, re.I) or re.search(r"\bshielded\b", chunk, re.I):
                attrs["apantallado"] = "si"

            products.append({
                "id": f"scraped-phoenix-{ref}",
                "brand": "phoenix-contact",
                "model": type_code,
                "name": f"Phoenix Contact {type_code}",
                "family": family_label or "Phoenix Contact",
                "leaf": leaf_id,
                "secondary_leaves": [],
                "desc": f"Ref. {ref}. {family_label or ''}",
                "url": f"https://www.phoenixcontact.com/en/products/{ref}",
                "image_url": None,
                "lifecycle": "active",
                "is_software": 0,
                "_page": page_num,
                "_pdf": filename,
                **attrs,
            })
    return products, len(seen_refs)


def main():
    print("Loading texts...")
    data = json.load(open("phoenix_pdf_texts.json", encoding="utf-8"))
    print(f"  {len(data)} PDFs loaded")

    all_products = []
    seen_global_refs = set()
    by_pdf_count = {}

    for filename, pdf_data in data.items():
        mapping = get_mapping(filename)
        leaf_id, leaf_label, family, is_catalog = mapping
        if not is_catalog:
            print(f"  [SKIP] {filename}: brochure/info")
            continue
        prods, n = parse_one_pdf(filename, pdf_data, mapping)
        # Dedupe contra global
        unique_added = 0
        for p in prods:
            ref = p["id"].split("-")[-1]
            if ref in seen_global_refs:
                continue
            seen_global_refs.add(ref)
            all_products.append(p)
            unique_added += 1
        by_pdf_count[filename] = unique_added
        print(f"  [OK]   {filename}: {unique_added} productos (de {n} encontrados)")

    print()
    print(f"Total productos Phoenix Contact: {len(all_products)}")
    by_leaf = defaultdict(int)
    for p in all_products:
        by_leaf[p["leaf"]] += 1
    print("Por leaf:")
    for leaf, n in sorted(by_leaf.items(), key=lambda kv: -kv[1]):
        print(f"  {leaf}: {n}")
    # Save
    with open("phoenix_products.json", "w", encoding="utf-8") as f:
        json.dump({"products": all_products}, f, ensure_ascii=False)
    import os
    sz = os.path.getsize("phoenix_products.json") / 1024 / 1024
    print(f"\nSaved phoenix_products.json ({sz:.1f} MB)")


if __name__ == "__main__":
    main()
