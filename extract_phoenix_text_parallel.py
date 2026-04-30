"""Extrae texto de los 59 PDFs Phoenix en paralelo (multiprocessing).
Output: phoenix_pdf_texts.json con {filename: [{page, text}, ...]}
"""
import os
import json
from multiprocessing import Pool


def extract_one(pdf_path):
    """Extrae texto y metadata básica de un PDF. Worker function."""
    try:
        import pypdf
        r = pypdf.PdfReader(pdf_path)
        pages = []
        for i, page in enumerate(r.pages):
            txt = page.extract_text() or ""
            pages.append({"page": i + 1, "text": txt})
        total_chars = sum(len(p["text"]) for p in pages)
        return {
            "ok": True,
            "filename": os.path.basename(pdf_path),
            "n_pages": len(pages),
            "total_chars": total_chars,
            "pages": pages,
        }
    except Exception as e:
        return {
            "ok": False,
            "filename": os.path.basename(pdf_path),
            "error": str(e),
        }


def main():
    pdf_dir = "Catalogos Phoenix"
    pdfs = sorted(
        os.path.join(pdf_dir, f) for f in os.listdir(pdf_dir)
        if f.lower().endswith(".pdf")
    )
    print(f"Found {len(pdfs)} PDFs")
    total_size_mb = sum(os.path.getsize(p) for p in pdfs) / (1024 * 1024)
    print(f"Total size: {total_size_mb:.0f} MB")

    n_workers = min(6, os.cpu_count() or 4)
    print(f"Using {n_workers} parallel workers...")

    results = {}
    with Pool(n_workers) as pool:
        for r in pool.imap_unordered(extract_one, pdfs, chunksize=1):
            fn = r.get("filename")
            if r.get("ok"):
                results[fn] = {
                    "n_pages": r["n_pages"],
                    "total_chars": r["total_chars"],
                    "pages": r["pages"],
                }
                print(f"  OK: {fn} ({r['n_pages']} pages, {r['total_chars']/1000:.0f}k chars)")
            else:
                print(f"  FAIL: {fn}: {r.get('error')}")

    # Guardar
    with open("phoenix_pdf_texts.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    sz = os.path.getsize("phoenix_pdf_texts.json") / (1024 * 1024)
    print(f"\nSaved phoenix_pdf_texts.json ({sz:.1f} MB)")
    print(f"PDFs procesados: {len(results)}/{len(pdfs)}")


if __name__ == "__main__":
    main()
