"""V2: Para cada producto sin imagen en su pagina propia, usar la imagen
de la pagina donde aparece la FAMILIA del producto (ej GTE6, IME08, S32B).

La familia se extrae del prefijo del modelo:
- GTE6-P1212 -> GTE6
- IME08-02BNSZT0S -> IME08
- V200-18-E1B -> V200
- S32B-2011BA -> S32B
"""
import fitz
import json
import base64
import hashlib
import re
import os
from collections import defaultdict
from parse_sick_pdf import parse_sick_pdf


def family_from_sku(sku):
    """Extrae el prefijo de familia del modelo SICK."""
    if not sku:
        return None
    s = sku.upper()
    # Casos: V200-18-E1B -> V200; GTE6-P1212 -> GTE6; IME08-02 -> IME08
    # Patrón simple: tomar hasta el primer guion, o hasta donde encontremos
    # cierto numero de digitos seguidos.
    if "-" in s:
        return s.split("-", 1)[0]
    # Sin guion: separar letras + primeros digitos
    m = re.match(r"([A-Z]+\d+)", s)
    if m:
        return m.group(1)
    return s[:6] if len(s) > 6 else s


def extract_main_image_per_page(pdf_path):
    doc = fitz.open(pdf_path)
    page_to_image = {}
    for i, page in enumerate(doc):
        page_num = i + 1
        best = None
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
            except Exception:
                continue
            w = base.get("width", 0)
            h = base.get("height", 0)
            data = base.get("image", b"")
            ext = base.get("ext", "png")
            if w < 80 or h < 80:
                continue
            if not data or len(data) < 1000:
                continue
            score = w * h
            if best is None or score > best["score"]:
                best = {"data": data, "ext": ext, "w": w, "h": h, "score": score}
        if best:
            page_to_image[page_num] = best
    return page_to_image


def main():
    print("Parsing products...")
    products, _ = parse_sick_pdf()
    print(f"  {len(products)} products")
    print("Extracting page images...")
    pti = extract_main_image_per_page("CATÁLOGO SICK.pdf")
    print(f"  {len(pti)} pages with image")

    # Por cada pagina con imagen, asociar la imagen a TODAS las familias mencionadas
    # en esa pagina (segun los productos extraidos).
    # Pero un producto y su variante pueden compartir familia → mismo imagen.
    family_to_image = {}  # family -> image dict (data, ext)
    pages_per_family = defaultdict(list)

    for p in products:
        fam = family_from_sku(p.get("model"))
        if fam:
            pages_per_family[fam].append(p["_page"])

    # Para cada familia, encontrar la pagina con imagen que tenga MAS productos
    # de esa familia. Esa es la pagina "hero" de la familia.
    for fam, pages in pages_per_family.items():
        # contar pages
        from collections import Counter
        page_counts = Counter(pages)
        # iterar pages by frequency desc
        for page, _cnt in page_counts.most_common():
            if page in pti:
                family_to_image[fam] = pti[page]
                break

    print(f"  Familias con imagen identificada: {len(family_to_image)}/{len(pages_per_family)}")

    # Asignar a cada producto la imagen de su pagina; si no, la de su familia
    matched_own_page = 0
    matched_family = 0
    no_image = 0
    img_data = {}  # hash -> (b64, mime)
    shared = defaultdict(list)  # hash -> [product_ids]

    for p in products:
        page = p["_page"]
        img = pti.get(page)
        source = "own_page"
        if not img:
            fam = family_from_sku(p.get("model"))
            if fam and fam in family_to_image:
                img = family_to_image[fam]
                source = "family"
        if not img:
            no_image += 1
            continue
        if source == "own_page":
            matched_own_page += 1
        else:
            matched_family += 1
        h = hashlib.sha1(img["data"]).hexdigest()
        if h not in img_data:
            mime = "image/jpeg" if img["ext"] in ("jpeg", "jpg") else f"image/{img['ext']}"
            img_data[h] = {
                "data_b64": base64.b64encode(img["data"]).decode("ascii"),
                "mime": mime,
            }
        shared[h].append(p["id"])

    total_matched = matched_own_page + matched_family
    print(f"\nMatched (su propia pagina): {matched_own_page}")
    print(f"Matched (imagen de familia): {matched_family}")
    print(f"Total con imagen: {total_matched}/{len(products)} ({100*total_matched/len(products):.0f}%)")
    print(f"Sin imagen: {no_image}")
    print(f"Imagenes unicas: {len(img_data)}")

    payload = {"images": []}
    for h, ids in shared.items():
        payload["images"].append({
            "product_ids": ids,
            "data_b64": img_data[h]["data_b64"],
            "mime": img_data[h]["mime"],
        })
    with open("sick_images_payload_v2.json", "w", encoding="utf-8") as f:
        json.dump(payload, f)
    sz = os.path.getsize("sick_images_payload_v2.json")
    print(f"\nPayload v2: sick_images_payload_v2.json ({sz/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
