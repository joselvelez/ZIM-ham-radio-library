"""Extract text and figures using the shared figure-geometry rules."""
from __future__ import annotations
import pymupdf as fitz
from pathlib import Path
from typing import Dict, Any, List
import html as html_lib

from .figures import figure_regions, is_label, is_diagram, is_path_heavy, is_prose_svg


def extract_page(page: fitz.Page) -> Dict[str, Any]:
    regions = figure_regions(page)
    blocks = page.get_text("blocks")

    body: List[dict] = []
    labels: List[dict] = []
    for b in sorted(blocks, key=lambda x: (x[1], x[0])):
        if b[6] != 0:
            continue
        text = b[4].strip()
        if not text:
            continue
        bbox = fitz.Rect(b[:4])
        entry = {"bbox": [bbox.x0, bbox.y0, bbox.x1, bbox.y1], "text": text}
        if is_label(bbox, regions):
            labels.append(entry)
        else:
            body.append(entry)

    return {
        "text_blocks": body,
        "label_blocks": labels,
        "has_native_vectors": bool(regions),
        "drawing_count": len(regions),
        "width": page.rect.width,
        "height": page.rect.height,
    }


def extract_pdf(pdf_path: Path, max_pages: int | None = None) -> Dict[str, Any]:
    """Extract pages. max_pages limits work for large manuals during prototype runs."""
    doc = fitz.open(pdf_path)
    total = doc.page_count
    limit = total if max_pages is None else min(max_pages, total)
    pages = []
    for i in range(limit):
        if i == 0 or (i + 1) % 10 == 0 or i == limit - 1:
            print(f"  extracting page {i + 1}/{limit} (of {total})")
        pages.append(extract_page(doc[i]))
    doc.close()
    return {"path": str(pdf_path), "page_count": total, "pages_extracted": limit, "pages": pages}


def extract_diagram_svg(page: fitz.Page, out_path: Path) -> str | None:
    """SVG of the main figure region via MuPDF (clip + get_svg_image).

    Uses is_diagram() so title/logo art is skipped by the same rule for every page.
    Also rejects path-heavy SVGs (text outlined as vectors) via is_path_heavy().
    """
    regions = figure_regions(page)
    if not regions:
        return None
    raw = page.get_text("blocks")
    text_blocks = [{"bbox": b[:4], "text": (b[4] or "").strip()}
                   for b in raw if b[6] == 0]
    diagrams = [r for r in regions if is_diagram(r, text_blocks)]
    if not diagrams:
        print("  no diagram region (clusters are title/logo art); skipping figure")
        return None
    region = max(diagrams, key=lambda r: r.get_area())
    clip = fitz.Rect(region.x0 - 4, region.y0 - 16, region.x1 + 4, region.y1 + 4) & page.rect

    tmp = fitz.open()
    tp = tmp.new_page(width=clip.width, height=clip.height)
    tp.show_pdf_page(tp.rect, page.parent, page.number, clip=clip)
    svg = tp.get_svg_image(text_as_path=False)
    tmp.close()

    if is_path_heavy(svg, region):
        print("  cluster is path-heavy (outlined text / logo); skipping figure")
        return None
    if is_prose_svg(svg):
        print("  cluster is body text, not a diagram; skipping figure")
        return None

    out_path.write_text(svg)
    return str(out_path)
