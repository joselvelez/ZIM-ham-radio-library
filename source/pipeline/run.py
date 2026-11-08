#!/usr/bin/env python3
"""Minimal prototype pipeline: ingest → extract → (vector stub) → HTML article.

Usage:
  python3 -m source.pipeline.run path/to/sample.pdf --category band-plans
"""
import argparse
import sys
from pathlib import Path

# Allow running as script from repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from source.pipeline.ingest import ingest_pdf
from source.pipeline.extract import extract_pdf, extract_native_svg_stub
from source.pipeline.assemble import write_article
import pymupdf as fitz

def ai_vectorize_stub(rendered_path: Path) -> str:
    """Placeholder for AI raster → accurate SVG recreation.
    In the real pipeline this would call an image-to-SVG model, iterate on fidelity,
    and return the SVG path. For the prototype we just note the path.
    """
    print(f"[AI vectorization stub] Would recreate diagram from {rendered_path}")
    return None  # no output for stub

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path, help="PDF to process")
    ap.add_argument("--category", default="band-plans")
    ap.add_argument("--html-root", type=Path, default=Path("html"))
    args = ap.parse_args()

    pdf = args.pdf.resolve()
    if not pdf.exists():
        print(f"PDF not found: {pdf}")
        sys.exit(1)

    print("=== 1. Ingest ===")
    record = ingest_pdf(pdf, category=args.category)

    print("=== 2. Extract ===")
    extracted = extract_pdf(pdf)
    print(f"Pages: {extracted['page_count']}, first page blocks: {len(extracted['pages'][0]['text_blocks']) if extracted['pages'] else 0}")
    print(f"Native vectors on page 0: {extracted['pages'][0].get('has_native_vectors')}")

    svg_path = None
    # Native vector path
    if extracted["pages"] and extracted["pages"][0].get("has_native_vectors"):
        print("=== 3. Native SVG export ===")
        svg_out = Path("source/notes") / f"{record['id']}-page0.svg"
        svg_out.parent.mkdir(exist_ok=True)
        doc = fitz.open(pdf)
        svg_path = extract_native_svg_stub(doc[0], svg_out)
        doc.close()
        print(f"SVG: {svg_path}")

    # Example AI path (even if we have native, show the stub)
    print("=== 3b. AI vectorization example path (stub) ===")
    # Render a page image for the AI path
    doc = fitz.open(pdf)
    pix = doc[0].get_pixmap(dpi=120)
    render_path = Path("source/notes") / f"{record['id']}-page0.png"
    pix.save(str(render_path))
    doc.close()
    ai_vectorize_stub(render_path)

    print("=== 4. Assemble HTML ===")
    article = write_article(record, extracted, args.html_root, svg_path if svg_path and Path(svg_path).exists() else None)
    print(f"Wrote article: {article}")

    # Update index (simple append)
    index = args.html_root / "index.html"
    if index.exists():
        content = index.read_text()
        link = f'<li><a href="articles/{args.category}/{article.name}">{article.stem.replace("-", " ").title()}</a></li>'
        if article.name not in content:
            # naive insert before </ul>
            content = content.replace("</ul>", f"    {link}\n  </ul>", 1)
            index.write_text(content)
            print("Updated index.html")

    print("Done. Prototype slice complete.")
    print("Next: open the HTML, check visual fidelity, and consider what a RAG chunk would see (text + figure caption/context).")

if __name__ == "__main__":
    main()
