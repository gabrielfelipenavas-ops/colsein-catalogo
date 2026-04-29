"""Genera JSON de productos scrapeados (fase 1: Unitronics + Janitza).
Uso:
    python scraped_products_phase1.py | curl -X POST <url>/api/admin/import-products-batch \
        -H "Content-Type: application/json" -H "X-Admin-Token: <tok>" -d @-

O dentro del proyecto: ejecutalo, guarda a archivo, importa con import-json.
"""
import json
import sys


def desc(specs):
    """Construye description corta a partir de specs."""
    parts = []
    if specs.get("display_size"):
        parts.append(f"Display {specs['display_size']}")
    if specs.get("digital_inputs") is not None:
        parts.append(f"DI {specs['digital_inputs']}")
    if specs.get("analog_inputs") is not None:
        parts.append(f"AI {specs['analog_inputs']}")
    if specs.get("transistor_outputs") is not None:
        parts.append(f"DO trans {specs['transistor_outputs']}")
    if specs.get("relay_outputs") is not None:
        parts.append(f"DO relay {specs['relay_outputs']}")
    if specs.get("operating_voltage") or specs.get("voltage"):
        parts.append(f"V {specs.get('operating_voltage') or specs.get('voltage')}")
    if specs.get("ethernet_ports"):
        parts.append(f"Eth {specs['ethernet_ports']}")
    return " · ".join(parts) or "Variante PLC Unitronics"


def to_int(v):
    """Convierte specs a int si es numérico, si no None."""
    if v is None: return None
    if isinstance(v, (int, float)): return int(v)
    if isinstance(v, str):
        s = v.strip()
        try: return int(s)
        except: return None
    return None


def make_unitronics(series_label, leaf_slug, series_url, variants):
    """Mapea variantes Unitronics a productos."""
    out = []
    series_default_img = SERIES_DEFAULT_IMAGES.get(series_label) if "SERIES_DEFAULT_IMAGES" in globals() else None
    for v in variants:
        sku = v.get("sku") or v.get("SKU") or ""
        if not sku:
            continue
        attrs = {}
        for k in ("display_size", "digital_inputs", "analog_inputs",
                  "transistor_outputs", "relay_outputs", "ethernet_ports",
                  "output_type", "voltage", "operating_voltage",
                  "touch_type", "resolution", "protection_rating",
                  "operating_temperature"):
            val = v.get(k)
            if val is None or val == "":
                continue
            # Numéricos como int
            if k in ("digital_inputs", "analog_inputs", "transistor_outputs",
                     "relay_outputs", "ethernet_ports"):
                iv = to_int(val)
                if iv is not None:
                    attrs[k] = iv
            else:
                attrs[k] = val
        # Merge voltage and operating_voltage into voltage_dc
        v_str = attrs.pop("operating_voltage", None) or attrs.pop("voltage", None)
        if v_str:
            attrs["voltaje_dc"] = v_str
        if attrs.get("display_size"):
            attrs["display_size"] = str(attrs["display_size"]).replace('"', '').strip()
        # IP/protección
        prot = attrs.pop("protection_rating", None)
        if prot:
            # extraer IP65, IP66, etc.
            import re
            m = re.search(r"IP\s*(\d{2}(?:\/\d+K?)?)", str(prot), re.I)
            if m:
                attrs["ip_rating"] = "IP" + m.group(1).replace(" ", "")
        # Imagen: la específica del producto si tiene; si no, la default de la serie
        img = v.get("image_url") if v.get("image_url") and "wp-content" in str(v.get("image_url")) else None
        if not img:
            img = series_default_img
        out.append({
            "id": f"scraped-unitronics-{series_label.lower().replace(' ', '')}-{sku.lower().replace(' ', '-')}",
            "brand": "unitronics",
            "model": sku,
            "name": f"Unitronics {sku} ({series_label})",
            "family": series_label,
            "leaf": f"colsein-online.unitronics.{leaf_slug}",
            "secondary_leaves": [],
            "desc": desc(v),
            "url": series_url,
            "image_url": img,
            "lifecycle": "active",
            "is_software": 0,
            **attrs,
        })
    return out


# ============================================================================
# DATA SCRAPED 2026-04-29 — Unitronics (~110 variants), Janitza (~15)
# ============================================================================

UNISTREAM5 = [
    {"sku": "US5-X5-B1", "display_size": "5 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 1, "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2023/01/IMG_6997-2-black-gray.webp"},
    {"sku": "US5-X10-B1", "display_size": "5 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 1, "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/09/Programmable-logic-controller-Unistream5-Front.png"},
    {"sku": "US5-X5-TR22", "display_size": "5 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC", "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/09/Programmable-logic-controller-Unistream5-side.jpg"},
    {"sku": "US5-X10-TR22", "display_size": "5 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "US5-X5-T24", "display_size": "5 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC", "output_type": "pnp"},
    {"sku": "US5-X10-T24", "display_size": "5 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "US5-X5-RA28", "display_size": "5 inches", "digital_inputs": 14, "analog_inputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "US5-X10-RA28", "display_size": "5 inches", "digital_inputs": 14, "analog_inputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "US5-X5-TA30", "display_size": "5 inches", "digital_inputs": 14, "analog_inputs": 2, "transistor_outputs": 10, "operating_voltage": "24VDC", "output_type": "pnp"},
    {"sku": "US5-X10-TA30", "display_size": "5 inches", "digital_inputs": 14, "analog_inputs": 2, "transistor_outputs": 10, "operating_voltage": "24VDC"},
    {"sku": "US5-X5-R38", "display_size": "5 inches", "digital_inputs": 24, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "US5-X10-R38", "display_size": "5 inches", "digital_inputs": 24, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "US5-X5-T42", "display_size": "5 inches", "digital_inputs": 24, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC", "output_type": "pnp"},
    {"sku": "US5-X10-T42", "display_size": "5 inches", "digital_inputs": 24, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC"},
    {"sku": "US5-X5-TA32", "display_size": "5 inches", "digital_inputs": 13, "analog_inputs": 6, "transistor_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "US5-X10-TA32", "display_size": "5 inches", "digital_inputs": 13, "analog_inputs": 6, "transistor_outputs": 8, "operating_voltage": "24VDC"},
]

UNISTREAM7 = [
    {"sku": "USC-P-B10", "display_size": "N/A", "operating_voltage": "12/24VDC", "ethernet_ports": 2},
    {"sku": "USP-070-B10", "display_size": "7 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 2, "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/plc-controller-UniStream-7-front.jpg"},
]

UNISTREAM10 = [
    {"sku": "USP-104-M10", "display_size": "10.4 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 2, "touch_type": "Capacitive Multi-Touch", "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2019/04/Programmable-logic-controller-UniStream-10.4Multi-Touch_750x750.jpg"},
    {"sku": "USP-104-B10", "display_size": "10.4 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 2, "touch_type": "TFT LCD"},
]

VISION1210 = [
    {"sku": "V200-18-E1B", "display_size": "12.1 inches", "digital_inputs": 16, "analog_inputs": 3, "transistor_outputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E2B", "display_size": "12.1 inches", "digital_inputs": 16, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E3XB", "display_size": "12.1 inches", "digital_inputs": 18, "analog_inputs": 4, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E4XB", "display_size": "12.1 inches", "digital_inputs": 18, "analog_inputs": 4, "transistor_outputs": 17, "relay_outputs": 4, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E5B", "display_size": "12.1 inches", "digital_inputs": 18, "analog_inputs": 3, "transistor_outputs": 17, "relay_outputs": 0, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E6B", "display_size": "12.1 inches", "digital_inputs": 18, "analog_inputs": 5, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E46B", "display_size": "12.1 inches", "digital_inputs": 18, "analog_inputs": 9, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC"},
    {"sku": "V200-18-E62B", "display_size": "12.1 inches", "digital_inputs": 30, "analog_inputs": 2, "transistor_outputs": 30, "relay_outputs": 0, "operating_voltage": "24VDC"},
]

VISION700 = [
    {"sku": "V700-V200-18-E1B", "display_size": "7 inches", "digital_inputs": 16, "analog_inputs": 3, "transistor_outputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1, "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-700-by-Unitronics-front.jpg"},
    {"sku": "V700-V200-18-E2B", "display_size": "7 inches", "digital_inputs": 16, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V700-V200-18-E3XB", "display_size": "7 inches", "digital_inputs": 18, "analog_inputs": 4, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V700-V200-18-E4XB", "display_size": "7 inches", "digital_inputs": 18, "analog_inputs": 4, "transistor_outputs": 17, "relay_outputs": 0, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V700-V200-18-E5B", "display_size": "7 inches", "digital_inputs": 18, "analog_inputs": 3, "transistor_outputs": 17, "relay_outputs": 0, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V700-V200-18-E6B", "display_size": "7 inches", "digital_inputs": 18, "analog_inputs": 5, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V700-V200-18-E46B", "display_size": "7 inches", "digital_inputs": 18, "analog_inputs": 9, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V700-V200-18-E62B", "display_size": "7 inches", "digital_inputs": 30, "analog_inputs": 2, "transistor_outputs": 30, "relay_outputs": 0, "operating_voltage": "24VDC", "ethernet_ports": 1},
]

VISION1040 = [
    {"sku": "V1040-V200-18-E1B", "display_size": "10.4 inches", "digital_inputs": 16, "analog_inputs": 3, "transistor_outputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1, "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-1040-by-Unitronics-front-1.jpg"},
    {"sku": "V1040-V200-18-E2B", "display_size": "10.4 inches", "digital_inputs": 16, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V1040-V200-18-E3XB", "display_size": "10.4 inches", "digital_inputs": 18, "analog_inputs": 4, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V1040-V200-18-E4XB", "display_size": "10.4 inches", "digital_inputs": 18, "analog_inputs": 4, "transistor_outputs": 17, "relay_outputs": 0, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V1040-V200-18-E5B", "display_size": "10.4 inches", "digital_inputs": 18, "analog_inputs": 3, "transistor_outputs": 17, "relay_outputs": 0, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V1040-V200-18-E6B", "display_size": "10.4 inches", "digital_inputs": 18, "analog_inputs": 5, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V1040-V200-18-E46B", "display_size": "10.4 inches", "digital_inputs": 18, "analog_inputs": 9, "transistor_outputs": 2, "relay_outputs": 15, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V1040-V200-18-E62B", "display_size": "10.4 inches", "digital_inputs": 30, "analog_inputs": 2, "transistor_outputs": 30, "relay_outputs": 0, "operating_voltage": "24VDC", "ethernet_ports": 1},
]

VISION350 = [
    {"sku": "V350-J-B1", "display_size": "3.5 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-B1", "display_size": "3.5 inches", "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-TR20", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-TR20", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-R34", "display_size": "3.5 inches", "digital_inputs": 22, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-R34", "display_size": "3.5 inches", "digital_inputs": 22, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-TR34", "display_size": "3.5 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-TR34", "display_size": "3.5 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-TR6", "display_size": "3.5 inches", "digital_inputs": 8, "analog_inputs": 6, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-TR6", "display_size": "3.5 inches", "digital_inputs": 8, "analog_inputs": 6, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-RA22", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-RA22", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-TRA22", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 4, "relay_outputs": 4, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-TRA22", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 4, "relay_outputs": 4, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-T2", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-T2", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-T38", "display_size": "3.5 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-T38", "display_size": "3.5 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-J-TA24", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-35-TA24", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-S-TA24", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
    {"sku": "V350-JS-TA24", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC", "ethernet_ports": 1},
]

VISION130 = [
    {"sku": "V130-J-B1", "display_size": "2.4 inches", "operating_voltage": "12/24VDC"},
    {"sku": "V130-33-B1", "display_size": "2.4 inches", "operating_voltage": "12/24VDC"},
    {"sku": "V130-J-TR20", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "V130-33-TR20", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "V130-J-R34", "display_size": "2.4 inches", "digital_inputs": 22, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "V130-33-R34", "display_size": "2.4 inches", "digital_inputs": 22, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "V130-J-TR34", "display_size": "2.4 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "V130-33-TR34", "display_size": "2.4 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "V130-J-TR6", "display_size": "2.4 inches", "digital_inputs": 8, "analog_inputs": 6, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "V130-33-TR6", "display_size": "2.4 inches", "digital_inputs": 8, "analog_inputs": 6, "transistor_outputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "V130-J-RA22", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "V130-33-RA22", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "V130-J-TRA22", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 4, "relay_outputs": 4, "operating_voltage": "24VDC"},
    {"sku": "V130-33-TRA22", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 4, "relay_outputs": 4, "operating_voltage": "24VDC"},
    {"sku": "V130-J-T2", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "V130-33-T2", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "V130-J-T38", "display_size": "2.4 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC"},
    {"sku": "V130-33-T38", "display_size": "2.4 inches", "digital_inputs": 22, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC"},
    {"sku": "V130-J-TA24", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC"},
    {"sku": "V130-33-TA24", "display_size": "2.4 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC"},
]

SAMBA43 = [
    {"sku": "SM43-J-R20", "display_size": "4.3 inches", "digital_inputs": 10, "analog_inputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC", "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/Programmable-controllers-Samba-4.3-by-Unitronics-front-1-1.jpg"},
    {"sku": "SM43-J-T20", "display_size": "4.3 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "SM43-J-RA22", "display_size": "4.3 inches", "digital_inputs": 12, "analog_inputs": 4, "relay_outputs": 10, "operating_voltage": "24VDC"},
    {"sku": "SM43-J-TA22", "display_size": "4.3 inches", "digital_inputs": 12, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC"},
]

JAZZ = [
    {"sku": "JZ20-J-R10", "digital_inputs": 6, "relay_outputs": 4, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-R16", "digital_inputs": 8, "relay_outputs": 16, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-R16HS", "digital_inputs": 8, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-R31", "digital_inputs": 18, "relay_outputs": 11, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-T10", "digital_inputs": 6, "transistor_outputs": 4, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-T18", "digital_inputs": 8, "transistor_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-T20HS", "digital_inputs": 8, "transistor_outputs": 10, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-T40", "digital_inputs": 18, "transistor_outputs": 20, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-UA24", "digital_inputs": 11, "analog_inputs": 2, "relay_outputs": 5, "transistor_outputs": 2, "operating_voltage": "24VDC"},
    {"sku": "JZ20-J-UN20", "digital_inputs": 11, "relay_outputs": 5, "transistor_outputs": 2, "operating_voltage": "24VDC"},
]

M91 = [
    {"sku": "M91-2-R1", "digital_inputs": 10, "analog_inputs": 1, "relay_outputs": 6, "operating_voltage": "12/24VDC"},
    {"sku": "M91-2-R2C", "digital_inputs": 10, "analog_inputs": 2, "relay_outputs": 6, "operating_voltage": "12/24VDC"},
    {"sku": "M91-2-R6C", "digital_inputs": 6, "analog_inputs": 6, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "M91-2-R34", "digital_inputs": 20, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "M91-2-T1", "digital_inputs": 12, "transistor_outputs": 12, "operating_voltage": "12/24VDC"},
    {"sku": "M91-2-T38", "digital_inputs": 22, "transistor_outputs": 16, "operating_voltage": "24VDC"},
    {"sku": "M91-2-T2C", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "12/24VDC"},
    {"sku": "M91-2-UN2", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "12/24VDC"},
    {"sku": "M91-2-UA2", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "M91-2-RA22", "digital_inputs": 8, "analog_inputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC"},
]

VISION430 = [
    {"sku": "V430-J-B1", "display_size": "4.3 inches", "operating_voltage": "12/24VDC"},
    {"sku": "V430-J-RH2", "display_size": "4.3 inches", "digital_inputs": 10, "analog_inputs": 2, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "V430-J-R34", "display_size": "4.3 inches", "digital_inputs": 20, "analog_inputs": 2, "relay_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "V430-J-TR34", "display_size": "4.3 inches", "digital_inputs": 20, "analog_inputs": 2, "transistor_outputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "V430-J-RH6", "display_size": "4.3 inches", "digital_inputs": 6, "analog_inputs": 6, "relay_outputs": 6, "operating_voltage": "24VDC"},
    {"sku": "V430-J-RA22", "display_size": "4.3 inches", "digital_inputs": 8, "analog_inputs": 4, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "V430-J-TRA22", "display_size": "4.3 inches", "digital_inputs": 8, "analog_inputs": 4, "transistor_outputs": 4, "relay_outputs": 4, "operating_voltage": "24VDC"},
    {"sku": "V430-J-T2", "display_size": "4.3 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 12, "operating_voltage": "24VDC"},
    {"sku": "V430-J-T38", "display_size": "4.3 inches", "digital_inputs": 20, "analog_inputs": 2, "transistor_outputs": 16, "operating_voltage": "24VDC"},
    {"sku": "V430-J-TA24", "display_size": "4.3 inches", "digital_inputs": 8, "analog_inputs": 4, "transistor_outputs": 10, "operating_voltage": "24VDC"},
]

VISION570 = [
    {"sku": "V570-57-T20B", "display_size": "5.7 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 1, "resolution": "320x240 QVGA"},
    {"sku": "V570-57-T20B-J", "display_size": "5.7 inches", "operating_voltage": "12/24VDC", "ethernet_ports": 1, "resolution": "320x240 QVGA"},
]

VISION560 = [
    {"sku": "V560-T25B", "display_size": "5.7 inches", "operating_voltage": "12/24VDC", "resolution": "320x240 QVGA"},
]

SAMBA35 = [
    {"sku": "SM35-J-R20", "display_size": "3.5 inches", "digital_inputs": 10, "analog_inputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC", "image_url": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/programmable-logic-controller-Samba-3.5-by-Unitronics-front.jpg"},
    {"sku": "SM35-J-T20", "display_size": "3.5 inches", "digital_inputs": 10, "analog_inputs": 2, "transistor_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "SM35-J-RA22", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 2, "relay_outputs": 8, "operating_voltage": "24VDC"},
    {"sku": "SM35-J-TA22", "display_size": "3.5 inches", "digital_inputs": 12, "analog_inputs": 2, "transistor_outputs": 8, "operating_voltage": "24VDC"},
]

# Imágenes default por serie (cuando una variante específica no trae la suya)
SERIES_DEFAULT_IMAGES = {
    "UniStream 5": "https://www.unitronicsplc.com/wp-content/uploads/2017/09/Programmable-logic-controller-Unistream5-Front.png",
    "UniStream 7": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/plc-controller-UniStream-7-front.jpg",
    "UniStream 10.4": "https://www.unitronicsplc.com/wp-content/uploads/2019/04/Programmable-logic-controller-UniStream-10.4Multi-Touch_750x750.jpg",
    "Vision 1210": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-1210-by-Unitronics-front-1.jpg",
    "Vision 700": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-700-by-Unitronics-front.jpg",
    "Vision 1040": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-1040-by-Unitronics-front-1.jpg",
    "Vision 350": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-350-by-Unitronics-front.jpg",
    "Vision 130": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-130-by-Unitronics-front.jpg",
    "Vision 430": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-430-by-Unitronics-front.jpg",
    "Vision 570": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-570-by-Unitronics-front.jpg",
    "Vision 560": "https://www.unitronicsplc.com/wp-content/uploads/2017/08/Programmable-logic-controller-Vision-560-by-Unitronics-front.jpg",
    "Samba 4.3": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/Programmable-controllers-Samba-4.3-by-Unitronics-front-1-1.jpg",
    "Samba 3.5": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/programmable-logic-controller-Samba-3.5-by-Unitronics-front.jpg",
    "Jazz": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/Programmable-controllers-Jazz-by-Unitronics-front.jpg",
    "M91": "https://www.unitronicsplc.com/wp-content/uploads/2017/07/Programmable-controllers-M91-by-Unitronics-front.jpg",
}


def janitza_products():
    """Productos Janitza scrapeados (con specs limitadas)."""
    base = [
        ("UMG 800", "Modular expandable energy analyzer for transparent energy flow measurement"),
        ("UMG 801", "Expandable modular power analyzer for energy consumption and power quality"),
        ("UMG 96-EL", "Power analyzer with Ethernet connectivity for data transmission"),
        ("UMG 96-PA", "Expandable modular power analyzer with residual current monitoring"),
        ("UMG 96-PQ-L", "Expandable modular power analyzer, modular configuration"),
        ("UMG 509-PRO", "Multi-functional power quality analyzer for grid assessment"),
        ("UMG 512-PRO", "Certified power quality analyzer (Class A) high accuracy"),
        ("UMG 604-PRO", "Functionally expandable power analyzer with modular capabilities"),
        ("RCM 201-ROGO", "Residual current monitoring with Rogowski current transformers"),
        ("RCM 202-AB", "Residual current analysis device, TYPE AB, leakage detection"),
        ("MRG Flex", "Mobile power analyzers for field-based power quality measurement"),
        ("ProData 2", "Data analysis and measurement tool for energy monitoring systems"),
        ("800-CT24", "Current measuring module for expandable measurement"),
        ("GridVis 9", "Power Grid Monitoring Software for network visualization"),
    ]
    out = []
    for name, desc_text in base:
        attrs = {"comunicacion_extra": "ethernet" if "Ethernet" in desc_text else None}
        attrs = {k: v for k, v in attrs.items() if v is not None}
        if "Class A" in desc_text:
            attrs["clase_precision"] = "A"
        if name.startswith("RCM"):
            leaf = "colsein-online.janitza.general"
        elif name.startswith("UMG"):
            leaf = "colsein-online.janitza.medidores-de-energia"
        else:
            leaf = "colsein-online.janitza.general"
        out.append({
            "id": f"scraped-janitza-{name.lower().replace(' ', '-').replace('.', '')}",
            "brand": "janitza",
            "model": name,
            "name": f"Janitza {name}",
            "family": "Janitza",
            "leaf": leaf,
            "secondary_leaves": [],
            "desc": desc_text,
            "url": "https://www.janitza.com/products.html",
            "image_url": None,
            "lifecycle": "active",
            "is_software": 1 if "Software" in desc_text else 0,
            **attrs,
        })
    return out


def all_products():
    out = []
    out.extend(make_unitronics("UniStream 5", "unistream", "https://www.unitronicsplc.com/unistream-series-unistream5/", UNISTREAM5))
    out.extend(make_unitronics("UniStream 7", "unistream", "https://www.unitronicsplc.com/unistream-series-unistream7/", UNISTREAM7))
    out.extend(make_unitronics("UniStream 10.4", "unistream", "https://www.unitronicsplc.com/unistream-series-unistream10/", UNISTREAM10))
    out.extend(make_unitronics("Vision 1210", "vision", "https://www.unitronicsplc.com/vision-series-vision1210/", VISION1210))
    out.extend(make_unitronics("Vision 700", "vision", "https://www.unitronicsplc.com/vision-series-vision700/", VISION700))
    out.extend(make_unitronics("Vision 1040", "vision", "https://www.unitronicsplc.com/vision-series-vision1040/", VISION1040))
    out.extend(make_unitronics("Vision 570", "vision", "https://www.unitronicsplc.com/vision-series-vision570/", VISION570))
    out.extend(make_unitronics("Vision 560", "vision", "https://www.unitronicsplc.com/vision-series-vision560/", VISION560))
    out.extend(make_unitronics("Vision 430", "vision", "https://www.unitronicsplc.com/vision-series-vision430/", VISION430))
    out.extend(make_unitronics("Vision 350", "vision", "https://www.unitronicsplc.com/vision-series-vision350/", VISION350))
    out.extend(make_unitronics("Vision 130", "vision", "https://www.unitronicsplc.com/vision-series-vision130/", VISION130))
    out.extend(make_unitronics("Samba 4.3", "samba", "https://www.unitronicsplc.com/samba-series-samba43/", SAMBA43))
    out.extend(make_unitronics("Samba 3.5", "samba", "https://www.unitronicsplc.com/samba-series-samba35/", SAMBA35))
    out.extend(make_unitronics("Jazz", "jazz", "https://www.unitronicsplc.com/jazz-series-jazz/", JAZZ))
    out.extend(make_unitronics("M91", "jazz", "https://www.unitronicsplc.com/m91-series-m91/", M91))
    out.extend(janitza_products())
    return out


if __name__ == "__main__":
    prods = all_products()
    print(json.dumps({"products": prods}, ensure_ascii=False), file=sys.stdout)
