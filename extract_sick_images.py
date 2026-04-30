"""Extrae imagen principal por pagina del PDF SICK y la asocia a los productos."""
import fitz
import json
import base64
from collections import defaultdict
from parse_sick_pdf import parse_sick_pdf


def extract_main_image_per_page(pdf_path):
    """Para cada pagina, devuelve la imagen mas grande (en bytes) que tenga
    al menos 100x100 pixeles. Esa suele ser la foto del producto."""
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
            # filtrar logos/iconos pequenos
            if w < 80 or h < 80:
                continue
            if not data or len(data) < 1000:
                continue
            score = w * h  # area
            if best is None or score > best["score"]:
                best = {
                    "data": data, "ext": ext,
                    "w": w, "h": h,
                    "score": score,
                }
        if best:
            page_to_image[page_num] = best
    return page_to_image


def main():
    print("Parsing products...")
    products, _ = parse_sick_pdf()
    print(f"  {len(products)} products parsed")
    print("Extracting page images...")
    pti = extract_main_image_per_page("CATÁLOGO SICK.pdf")
    print(f"  {len(pti)} pages with main image")
    # Asociar producto -> imagen
    associations = []  # (product_id, image_blob_b64, mime)
    pages_with_imgs = set(pti.keys())
    pages_with_prods = set(p["_page"] for p in products)
    pages_both = pages_with_imgs & pages_with_prods
    print(f"  Pages with both products and images: {len(pages_both)}")

    # Cache de imagenes ya codificadas (multiple productos comparten imagen de una pagina)
    page_b64_cache = {}
    matched = 0
    for p in products:
        page = p["_page"]
        img = pti.get(page)
        if not img:
            continue
        if page not in page_b64_cache:
            mime = "image/jpeg" if img["ext"] in ("jpeg", "jpg") else f"image/{img['ext']}"
            page_b64_cache[page] = (
                base64.b64encode(img["data"]).decode("ascii"),
                mime,
                len(img["data"])
            )
        b64, mime, sz = page_b64_cache[page]
        associations.append({"id": p["id"], "data_b64": b64, "mime": mime})
        matched += 1
    print(f"  Products matched to image: {matched}/{len(products)}")
    # Cuanto pesa el payload?
    total_size = sum(len(a["data_b64"]) for a in associations)
    print(f"  Total payload size: {total_size / 1024 / 1024:.1f} MB (base64)")

    # Por eficiencia, generar OTRO formato: shared images (1 image -> N product_ids)
    shared = defaultdict(list)  # img_hash -> [product_ids]
    img_data = {}  # img_hash -> {data_b64, mime, size}
    import hashlib
    for p in products:
        page = p["_page"]
        img = pti.get(page)
        if not img:
            continue
        h = hashlib.sha1(img["data"]).hexdigest()
        if h not in img_data:
            mime = "image/jpeg" if img["ext"] in ("jpeg", "jpg") else f"image/{img['ext']}"
            img_data[h] = {
                "data_b64": base64.b64encode(img["data"]).decode("ascii"),
                "mime": mime,
            }
        shared[h].append(p["id"])
    print(f"  Unique images: {len(img_data)} (avg {matched / max(1, len(img_data)):.1f} products per image)")
    payload = {"images": []}
    for h, ids in shared.items():
        payload["images"].append({
            "product_ids": ids,
            "data_b64": img_data[h]["data_b64"],
            "mime": img_data[h]["mime"],
        })
    with open("sick_images_payload.json", "w", encoding="utf-8") as f:
        json.dump(payload, f)
    sz = 0
    import os
    sz = os.path.getsize("sick_images_payload.json")
    print(f"  Payload guardado: sick_images_payload.json ({sz / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
