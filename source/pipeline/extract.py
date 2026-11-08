"""Extract text and figures using the shared figure-geometry rules."""
from __future__ import annotations
import pymupdf as fitz
from pathlib import Path
from typing import Dict, Any, List
import html as html_lib

from .figures import figure_regions, is_label, is_diagram, is_rule, is_barcode, is_path_art
from .layout import column_order, UnclassifiableLayout
from .svg_optimize import optimize_svg, BadSVG


def extract_page(page: fitz.Page) -> Dict[str, Any]:
    regions = figure_regions(page)
    blocks = page.get_text("blocks")

    body: List[dict] = []
    labels: List[dict] = []
    for b in blocks:
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

    # Reading order: left column fully, then right. Fail Fast on unclassifiable overlaps.
    try:
        body = column_order(body, page.rect.width)
    except UnclassifiableLayout as exc:
        raise SystemExit(f"Unclassifiable layout on page {page.number + 1}: {exc}") from exc

    return {
        "text_blocks": body,
        "label_blocks": labels,
        "has_native_vectors": bool(regions),
        "drawing_count": len(regions),
        "width": page.rect.width,
        "height": page.rect.height,
    }


def extract_pdf(pdf_path: Path, max_pages: int | None = None) -> Dict[str, Any]:
    """Extract pages.

    Default is the full document. max_pages is an explicit debug limit only;
    it is never applied silently. Callers that want the limit must pass it
    and must have already validated the debug context.
    """
    doc = fitz.open(pdf_path)
    total = doc.page_count
    if max_pages is not None and max_pages < 1:
        doc.close()
        raise SystemExit("--pages must be a positive integer")
    limit = total if max_pages is None else min(max_pages, total)
    if max_pages is not None and limit < total:
        print(f"  [debug] limiting extraction to {limit} of {total} pages")
    pages = []
    for i in range(limit):
        if i == 0 or (i + 1) % 10 == 0 or i == limit - 1:
            print(f"  extracting page {i + 1}/{limit} (of {total})")
        pages.append(extract_page(doc[i]))
    doc.close()
    return {"path": str(pdf_path), "page_count": total, "pages_extracted": limit, "pages": pages}


def extract_diagram_svgs(page: fitz.Page, out_dir: Path, stem: str) -> list[dict]:
    """SVG of every diagram region on the page.

    Rejects rules (thin, page-wide), barcodes (regular vertical bars),
    path-art (outlined logos and titles), and body text.
    One file per remaining region. Each SVG is run through the conservative
    optimizer before it is written.

    Returns a list of dicts: {path, page, bbox, labels}.
    Fail Fast if an SVG cannot be optimized.
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
        tmp = fitz.open()
        tp = tmp.new_page(width=clip.width, height=clip.height)
        tp.show_pdf_page(tp.rect, page.parent, page.number, clip=clip)
        svg = tp.get_svg_image(text_as_path=False)
        tmp.close()
        try:
            svg = optimize_svg(svg)
        except BadSVG as exc:
            raise SystemExit(f"SVG optimization failed for {stem}-{n}: {exc}") from exc
        out = out_dir / f"{stem}-{n}.svg"
        out.write_text(svg)
        # Labels that intersect this region (already classified by is_label logic)
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
