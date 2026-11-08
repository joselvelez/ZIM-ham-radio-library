"""Extract text and figures using the shared figure-geometry rules."""
from __future__ import annotations
import pymupdf as fitz
from pathlib import Path
from typing import Dict, Any, List
import html as html_lib

from .figures import drawing_regions, is_label

def extract_page(page: fitz.Page) -> Dict[str, Any]:
    regions = drawing_regions(page)
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

def extract_pdf(pdf_path: Path) -> Dict[str, Any]:
    doc = fitz.open(pdf_path)
    pages = [extract_page(p) for p in doc]
    doc.close()
    return {"path": str(pdf_path), "page_count": len(pages), "pages": pages}

def extract_diagram_svg(page: fitz.Page, out_path: Path) -> str | None:
    """SVG of the figure only: vector items inside drawing regions + their labels.
    Uses the same region definition as text classification.
    """
    regions = drawing_regions(page)
    if not regions:
        return None

    # Overall figure box (for viewBox), expanded just enough for labels
    u = regions[0]
    for r in regions[1:]:
        u |= r
    u = fitz.Rect(u.x0 - 4, u.y0 - 16, u.x1 + 4, u.y1 + 4)
    u &= page.rect

    scale = 1.4
    vw, vh = u.width * scale, u.height * scale

    def hx(c):
        if not c or len(c) < 3:
            return "#888888"
        return "#{:02x}{:02x}{:02x}".format(int(c[0]*255), int(c[1]*255), int(c[2]*255))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw:.0f} {vh:.0f}" width="100%" style="background:#1a2230;font-family:system-ui,sans-serif">',
    ]

    # Vectors that intersect any region
    for d in page.get_drawings():
        fill, stroke = hx(d.get("fill")), hx(d.get("color"))
        for item in d.get("items", []):
            if item[0] == "re":
                r = fitz.Rect(item[1])
                if not any(r.intersects(reg) for reg in regions):
                    continue
                x = (r.x0 - u.x0) * scale
                y = (r.y0 - u.y0) * scale
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{r.width*scale:.1f}" height="{r.height*scale:.1f}" '
                    f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
                )
            elif item[0] == "l":
                p1, p2 = item[1], item[2]
                mid = fitz.Point((p1.x+p2.x)/2, (p1.y+p2.y)/2)
                if not any(reg.contains(mid) for reg in regions):
                    continue
                x1, y1 = (p1.x - u.x0) * scale, (p1.y - u.y0) * scale
                x2, y2 = (p2.x - u.x0) * scale, (p2.y - u.y0) * scale
                parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="1"/>')

    # Labels: words that the shared rule classifies as labels
    for w in page.get_text("words"):
        wr = fitz.Rect(w[:4])
        if not is_label(wr, regions):
            continue
        x = (wr.x0 - u.x0) * scale + 2
        y = (wr.y1 - u.y0) * scale - 1
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="#eee" font-size="11">{html_lib.escape(w[4])}</text>')

    parts.append("</svg>")
    out_path.write_text("\n".join(parts))
    return str(out_path)
