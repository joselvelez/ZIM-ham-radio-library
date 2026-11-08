#!/usr/bin/env python3
"""Pipeline: ingest → extract → (vector stub) → quality → HTML → stable index.

Usage:
  python3 source/pipeline/run.py path/to/file.pdf --category band-plans
  python3 source/pipeline/run.py source/pdfs/public/basic/ --category band-plans
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from source.pipeline.ingest import ingest_pdf
from source.pipeline.extract import extract_pdf, extract_diagram_svg
from source.pipeline.assemble import write_article
from source.pipeline.quality import score_document, enqueue_if_low
from source.pipeline.index import rebuild_index
import pymupdf as fitz

def ai_vectorize_stub(rendered_path: Path) -> str | None:
    """Placeholder for AI raster → accurate SVG recreation."""
    print(f"[AI vectorization stub] Would recreate diagram from {rendered_path}")
    return None

def process_one(pdf: Path, category: str, html_root: Path) -> None:
    print(f"\n=== Processing {pdf.name} ===")
    record = ingest_pdf(pdf, category=category)

    extracted = extract_pdf(pdf)
    pages = extracted.get("pages", [])
    print(f"Pages: {extracted['page_count']}, body blocks on p0: {len(pages[0]['text_blocks']) if pages else 0}")
    print(f"Native vectors on p0: {pages[0].get('has_native_vectors') if pages else False}")

    svg_path = None
    if pages and pages[0].get("has_native_vectors"):
        svg_out = Path("source/notes") / f"{record['id']}-page0.svg"
        svg_out.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(pdf)
        svg_path = extract_diagram_svg(doc[0], svg_out)
        doc.close()
        print(f"SVG: {svg_path}")

    # AI path stub (always noted; real call replaces this)
    doc = fitz.open(pdf)
    pix = doc[0].get_pixmap(dpi=120)
    render_path = Path("source/notes") / f"{record['id']}-page0.png"
    pix.save(str(render_path))
    doc.close()
    ai_vectorize_stub(render_path)

    svg_ok = bool(svg_path and Path(svg_path).exists())
    quality = score_document(extracted, svg_ok)
    print(f"Score: {quality['score']} (text={quality['text_score']}, figure={quality['figure_score']}, cpp={quality['chars_per_page']})")
    review = enqueue_if_low(record, quality)
    if review:
        print(f"Queued for review: {review}")

    article = write_article(record, extracted, html_root, svg_path if svg_ok else None)
    print(f"Article: {article}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path, help="PDF file or directory of PDFs")
    ap.add_argument("--category", default="band-plans")
    ap.add_argument("--html-root", type=Path, default=Path("html"))
    args = ap.parse_args()

    target = args.path.resolve()
    if not target.exists():
        print(f"Not found: {target}")
        sys.exit(1)

    pdfs = sorted(target.glob("*.pdf")) if target.is_dir() else [target]
    if not pdfs:
        print(f"No PDFs in {target}")
        sys.exit(1)

    for pdf in pdfs:
        process_one(pdf, args.category, args.html_root)

    rebuild_index(args.html_root)
    print("\nIndex rebuilt.")
    print("Done.")

if __name__ == "__main__":
    main()
