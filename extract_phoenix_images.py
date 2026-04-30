"""Extrae imagenes embebidas de los PDFs Phoenix Contact y las asocia a
los productos por pagina. Misma logica que extract_sick_images_v2 pero
multi-PDF.
"""
import fitz
import json
import base64
import hashlib
import re
import os
from collections import defaultdict


def family_from_phoenix_sku(sku):
    """Extrae prefijo de familia del SKU Phoenix.
    Ej: MCV 1,5/ 2-G-3,5 -> MCV
        QUINT-PS-100-240AC -> QUINT
        UT 4-D -> UT
    """
    if not sku:
        return None
    s = sku.upper().strip()
    # Tomar la primera "palabra" alfa (hasta primer espacio, digito, slash o coma)
    m = re.match(r"([A-Z][A-Z0-9-]*?)(?=[\s/,]|\d)", s)
    if m and len(m.group(1)) >= 2:
        return m.group(1)
    # fallback
    return s.split()[0][:8] if s else None


def extract_main_image_per_page(pdf_path):
    """Para cada pagina, devuelve la imagen mas grande (bytes)."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"    ERROR opening {pdf_path}: {e}")
        return {}
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
    doc.close()
    return page_to_image


def main():
    print("Loading phoenix_products.json...")
    products = json.load(open("phoenix_products.json", encoding="utf-8"))["products"]
    print(f"  {len(products)} productos")

    # Indexar productos por (pdf, page)
    by_pdf_page = defaultdict(list)
    for p in products:
        pdf = p.get("_pdf")
        page = p.get("_page")
        if pdf and page:
            by_pdf_page[(pdf, page)].append(p)

    pdfs_to_process = sorted(set(p.get("_pdf") for p in products if p.get("_pdf")))
    print(f"  {len(pdfs_to_process)} PDFs distintos")

    # Extract imágenes por PDF
    pdf_images = {}  # pdf_filename -> {page: {data, ext, w, h}}
    pdf_dir = "Catalogos Phoenix"
    for i, pdf_filename in enumerate(pdfs_to_process):
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        if not os.path.exists(pdf_path):
            print(f"  [SKIP] {pdf_filename}: not found")
            continue
        print(f"  [{i+1}/{len(pdfs_to_process)}] Extracting from {pdf_filename}...")
        pdf_images[pdf_filename] = extract_main_image_per_page(pdf_path)
        print(f"      {len(pdf_images[pdf_filename])} pages with image")

    # Familia -> imagen (fallback)
    family_to_image = {}
    pages_per_family_per_pdf = defaultdict(lambda: defaultdict(list))
    for p in products:
        fam = family_from_phoenix_sku(p.get("model"))
        pdf = p.get("_pdf")
        page = p.get("_page")
        if fam and pdf and page:
            pages_per_family_per_pdf[pdf][fam].append(page)
    # Para cada (pdf, familia), elegir la pagina mas frecuente que tenga imagen
    for pdf, fam_dict in pages_per_family_per_pdf.items():
        for fam, pages in fam_dict.items():
            from collections import Counter
            page_counts = Counter(pages)
            for page, _ in page_counts.most_common():
                if page in pdf_images.get(pdf, {}):
                    family_to_image[(pdf, fam)] = pdf_images[pdf][page]
                    break

    print(f"\n  Familias con imagen identificada: {len(family_to_image)}")

    # Asignar imagenes a productos
    matched_own = 0
    matched_family = 0
    no_image = 0
    img_data = {}  # hash -> {data_b64, mime}
    shared = defaultdict(list)  # hash -> [product_ids]

    for p in products:
        pdf = p.get("_pdf")
        page = p.get("_page")
        img = None
        # 1. Pagina propia
        if pdf and page and page in pdf_images.get(pdf, {}):
            img = pdf_images[pdf][page]
            matched_own += 1
        else:
            # 2. Familia
            fam = family_from_phoenix_sku(p.get("model"))
            if fam and (pdf, fam) in family_to_image:
                img = family_to_image[(pdf, fam)]
                matched_family += 1
        if not img:
            no_image += 1
            continue
        h = hashlib.sha1(img["data"]).hexdigest()
        if h not in img_data:
            mime = "image/jpeg" if img["ext"] in ("jpeg", "jpg") else f"image/{img['ext']}"
            img_data[h] = {
                "data_b64": base64.b64encode(img["data"]).decode("ascii"),
                "mime": mime,
            }
        shared[h].append(p["id"])

    total_matched = matched_own + matched_family
    print(f"\n  Matched (own page): {matched_own}")
    print(f"  Matched (family fallback): {matched_family}")
    print(f"  Total con imagen: {total_matched}/{len(products)} ({100*total_matched/len(products):.0f}%)")
    print(f"  Sin imagen: {no_image}")
    print(f"  Imagenes unicas: {len(img_data)}")

    # Generar payloads chunkeados
    os.makedirs("phoenix_images_chunks", exist_ok=True)
    # Cada chunk no debe exceder ~10 MB (en base64). Agrupar imagenes hasta ese limite.
    chunks = []
    current = {"images": []}
    current_size = 0
    MAX_CHUNK_BYTES = 10 * 1024 * 1024
    for h, ids in shared.items():
        item = {
            "product_ids": ids,
            "data_b64": img_data[h]["data_b64"],
            "mime": img_data[h]["mime"],
        }
        item_size = len(json.dumps(item))
        if current_size + item_size > MAX_CHUNK_BYTES and current["images"]:
            chunks.append(current)
            current = {"images": []}
            current_size = 0
        current["images"].append(item)
        current_size += item_size
    if current["images"]:
        chunks.append(current)
    for i, ch in enumerate(chunks):
        path = f"phoenix_images_chunks/chunk_{i+1:02d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ch, f)
        sz = os.path.getsize(path) / 1024 / 1024
        n_imgs = len(ch["images"])
        n_prods = sum(len(it["product_ids"]) for it in ch["images"])
        print(f"  chunk_{i+1:02d}.json: {n_imgs} imagenes ({n_prods} productos), {sz:.1f} MB")
    print(f"\nTotal chunks: {len(chunks)}")


if __name__ == "__main__":
    main()
