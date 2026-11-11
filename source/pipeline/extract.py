"""Extract text via pymupdf4llm (with layout) and figures as high-DPI PNG.

Body text, headings, reading order, and tables come from pymupdf4llm with
the pymupdf-layout engine activated. That is the maintained path; we do not
reimplement layout or table detection.

Figures are clipped regions rasterized at high DPI. Clipped SVG from
get_svg_image is incomplete (MuPDF maintainer guidance); a pixmap of the
region is the usable output.
"""
from __future__ import annotations
import pymupdf as fitz
# Layout must be imported and activated before pymupdf4llm.
import pymupdf.layout
pymupdf.layout.activate()
import pymupdf4llm
from pathlib import Path
from typing import Dict, Any, List

from .figures import figure_regions, is_diagram, is_rule, is_barcode, is_path_art

# Strip repeating page chrome. pymupdf4llm applies these as margins.
PAGE_MARGINS = (0, 50, 0, 50)
FIGURE_DPI = 200


# A single page is a chart or poster, not a reflowable manual.
def is_poster(page_count: int) -> bool:
    """True when the document is one page. Reflow would destroy it."""
    return page_count == 1


def render_page_png(page: fitz.Page, out_dir: Path, stem: str) -> dict:
    """High-DPI render of the whole page. Fail Fast if the write fails."""
    pix = page.get_pixmap(dpi=FIGURE_DPI)
    out = out_dir / f"{stem}-page.png"
    pix.save(str(out))
    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"Page PNG write failed for {out}")
    return {"path": str(out), "page": page.number, "labels": []}


def extract_pdf(pdf_path: Path, max_pages: int | None = None) -> Dict[str, Any]:
    """Extract the document as per-page markdown chunks.

    Default is the full document. max_pages is an explicit debug limit only.
    Fail Fast if pymupdf4llm returns no text.
    """
    doc = fitz.open(pdf_path)
    total = doc.page_count
    doc.close()
    if max_pages is not None and max_pages < 1:
        raise SystemExit("--pages must be a positive integer")
    pages = list(range(total if max_pages is None else min(max_pages, total)))
    if max_pages is not None and len(pages) < total:
        print(f"  [debug] limiting extraction to {len(pages)} of {total} pages")

    chunks = pymupdf4llm.to_markdown(
        str(pdf_path),
        pages=pages,
        page_chunks=True,
        margins=PAGE_MARGINS,
        header=False,
        footer=False,
    )
    if not chunks:
        raise SystemExit(f"pymupdf4llm returned no pages for {pdf_path.name}")
    text = "\n".join(c.get("text", "") for c in chunks)
    if not text.strip():
        raise SystemExit(f"pymupdf4llm returned empty text for {pdf_path.name}")

    return {
        "path": str(pdf_path),
        "page_count": total,
        "pages_extracted": len(chunks),
        "chunks": chunks,
    }


def extract_diagram_pngs(page: fitz.Page, out_dir: Path, stem: str) -> list[dict]:
    """High-DPI PNG of every diagram region on the page.

    Rejects rules, barcodes, path-art, and body text. One PNG per region.
    Fail Fast if a pixmap cannot be written.
    """
    regions = figure_regions(page)
    if not regions:
        return []
    raw = page.get_text("blocks")
    text_blocks = [{"bbox": b[:4], "text": (b[4] or "").strip()}
                   for b in raw if b[6] == 0]
    diagrams = [r for r in regions
                if not is_rule(r)
                and not is_barcode(r, page)
                and not is_path_art(r, page)
                and is_diagram(r, text_blocks)]
    if not diagrams:
        return []
    written: list[dict] = []
    for n, region in enumerate(sorted(diagrams, key=lambda r: (r.y0, r.x0))):
        clip = fitz.Rect(region.x0 - 4, region.y0 - 4, region.x1 + 4, region.y1 + 4) & page.rect
        pix = page.get_pixmap(clip=clip, dpi=FIGURE_DPI)
        out = out_dir / f"{stem}-{n}.png"
        pix.save(str(out))
        if not out.exists() or out.stat().st_size == 0:
            raise SystemExit(f"PNG write failed for {out}")
        labels = []
        for tb in text_blocks:
            bb = fitz.Rect(tb["bbox"])
            if not (region & bb).is_empty and tb["text"]:
                labels.append(tb["text"])
        written.append({
            "path": str(out),
            "page": page.number,
            "bbox": [region.x0, region.y0, region.x1, region.y1],
            "labels": labels,
        })
    return written
