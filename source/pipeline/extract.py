"""Extract text and figures using the shared figure-geometry rules."""
from __future__ import annotations
import pymupdf as fitz
from pathlib import Path
from typing import Dict, Any, List
from collections import Counter

from .figures import figure_regions, is_label, is_diagram, is_rule, is_barcode, is_path_art
from .layout import column_order, UnclassifiableLayout
from .svg_optimize import optimize_svg, BadSVG
from .structure import body_font_size, role_for_size, is_page_chrome, dehyphenate, NoBodyFont


def _span_blocks(page: fitz.Page) -> List[dict]:
    """Text blocks with dominant font size, from get_text('dict')."""
    raw = page.get_text("dict")
    out = []
    for b in raw.get("blocks", []):
        if b.get("type") != 0:
            continue
        sizes: Counter = Counter()
        parts = []
        for line in b.get("lines", []):
            line_text = []
            for s in line.get("spans", []):
                t = s.get("text") or ""
                if t:
                    sizes[round(s.get("size", 0), 1)] += len(t)
                    line_text.append(t)
            if line_text:
                parts.append("".join(line_text))
        text = "\n".join(parts).strip()
        if not text:
            continue
        size = sizes.most_common(1)[0][0] if sizes else 0
        bb = b.get("bbox") or (0, 0, 0, 0)
        out.append({
            "bbox": [bb[0], bb[1], bb[2], bb[3]],
            "text": text,
            "size": size,
        })
    return out


def extract_page(page: fitz.Page, body_size: float) -> Dict[str, Any]:
    regions = figure_regions(page)
    blocks = _span_blocks(page)

    body: List[dict] = []
    labels: List[dict] = []
    height = page.rect.height
    for b in blocks:
        text = dehyphenate(b["text"])
        bbox = fitz.Rect(b["bbox"])
        if is_page_chrome(text, b["size"], bbox.y0, bbox.y1, height, body_size):
            continue
        role = role_for_size(b["size"], body_size)
        entry = {"bbox": b["bbox"], "text": text, "role": role, "size": b["size"]}
        if is_label(bbox, regions):
            labels.append(entry)
        else:
            body.append(entry)

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
        "height": height,
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

    # Body font from a sample of pages. Fail Fast if it cannot be determined.
    sample_sizes = []
    for i in range(min(limit, 20)):
        for b in _span_blocks(doc[i]):
            sample_sizes.extend([b["size"]] * max(1, len(b["text"]) // 10))
    try:
        body_size = body_font_size(sample_sizes)
    except NoBodyFont as exc:
        doc.close()
        raise SystemExit(f"Cannot determine body font: {exc}") from exc
    print(f"  body font: {body_size}pt")

    pages = []
    for i in range(limit):
        if i == 0 or (i + 1) % 10 == 0 or i == limit - 1:
            print(f"  extracting page {i + 1}/{limit} (of {total})")
        pages.append(extract_page(doc[i], body_size))
    doc.close()
    return {"path": str(pdf_path), "page_count": total, "pages_extracted": limit, "pages": pages, "body_font": body_size}


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
