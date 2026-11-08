"""Figure geometry — single source of truth.

A "figure region" is the tight union of native vector drawing items on a page.
Text whose bounding box intersects that region (plus a small margin) is a label.
Everything else is body text.

Used by both text classification and SVG generation so the rule lives in one place.
"""
from __future__ import annotations
import pymupdf as fitz
from typing import List, Tuple

LABEL_MARGIN = 18  # points

def drawing_regions(page: fitz.Page) -> List[fitz.Rect]:
    """Tight rectangles covering native vector items. Merged if they overlap or nearly touch."""
    rects: List[fitz.Rect] = []
    for d in page.get_drawings():
        for item in d.get("items", []):
            kind = item[0]
            if kind == "re":
                rects.append(fitz.Rect(item[1]))
            elif kind == "l":
                p1, p2 = item[1], item[2]
                rects.append(fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y),
                                       max(p1.x, p2.x), max(p1.y, p2.y)))
            elif kind == "c":  # curve — approximate with control points
                pts = item[1]
                if pts:
                    xs = [p.x for p in pts]
                    ys = [p.y for p in pts]
                    rects.append(fitz.Rect(min(xs), min(ys), max(xs), max(ys)))
    return _merge(rects)

def _merge(rects: List[fitz.Rect], gap: float = 2) -> List[fitz.Rect]:
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    out = [rects[0]]
    for r in rects[1:]:
        last = out[-1]
        test = fitz.Rect(last.x0 - gap, last.y0 - gap, last.x1 + gap, last.y1 + gap)
        if test.intersects(r):
            out[-1] = last | r
        else:
            out.append(r)
    return out

def is_label(bbox: fitz.Rect, regions: List[fitz.Rect]) -> bool:
    """True if this text bbox belongs to a figure (intersects a drawing region + margin)."""
    if not regions:
        return False
    for r in regions:
        expanded = fitz.Rect(r.x0 - LABEL_MARGIN, r.y0 - LABEL_MARGIN,
                             r.x1 + LABEL_MARGIN, r.y1 + LABEL_MARGIN)
        if bbox.intersects(expanded):
            return True
    return False
