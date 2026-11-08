"""Figure geometry — single source of truth.

Figure regions come from page.cluster_drawings() (C-side clustering).
Text whose bbox intersects a region (+ margin) is a label; everything else is body.
SVG is produced by clipping to the region and calling get_svg_image (also C-side).
No Python reconstruction of individual paths.
"""
from __future__ import annotations
import pymupdf as fitz
from typing import List

LABEL_MARGIN = 18

def figure_regions(page: fitz.Page) -> List[fitz.Rect]:
    """Clustered vector regions on the page. Fast; implemented in MuPDF."""
    try:
        rects = page.cluster_drawings()
    except Exception:
        rects = []
    # drop tiny noise (rules, underlines)
    return [r for r in rects if r.width > 20 and r.height > 12]

def is_label(bbox: fitz.Rect, regions: List[fitz.Rect]) -> bool:
    if not regions:
        return False
    for r in regions:
        expanded = fitz.Rect(r.x0 - LABEL_MARGIN, r.y0 - LABEL_MARGIN,
                             r.x1 + LABEL_MARGIN, r.y1 + LABEL_MARGIN)
        if bbox.intersects(expanded):
            return True
    return False

def is_diagram(region: fitz.Rect, text_blocks: list) -> bool:
    """A region is a diagram when vector area substantially exceeds overlapping text.
    Title/logo art is mostly text (or text-sized); real diagrams are not.
    Single rule, no page-specific thresholds.
    """
    text_area = 0.0
    for b in text_blocks:
        bb = fitz.Rect(b["bbox"]) if isinstance(b, dict) else fitz.Rect(b[:4])
        inter = region & bb
        if not inter.is_empty:
            text_area += inter.get_area()
    region_area = region.get_area()
    if region_area <= 0:
        return False
    # diagram if drawings dominate the region (text covers less than half)
    return (text_area / region_area) < 0.5
