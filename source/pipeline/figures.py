"""Figure geometry — single source of truth.

Figure regions come from page.cluster_drawings() (C-side clustering).
Text whose bbox intersects a region (+ margin) is a label; everything else is body.
SVG is produced by clipping to the region and calling get_svg_image (also C-side).
No Python reconstruction of individual paths.

A region is a diagram only when nearby text does not dominate it. Cover logos and
header art sit next to titles and addresses; real diagrams do not. One rule for
every page and every PDF.
"""
from __future__ import annotations
import re
import pymupdf as fitz
from typing import List

LABEL_MARGIN = 18
# Search this far outside the cluster so adjacent title/address text counts.
NEAR_MARGIN = 36
# Nearby text covering this fraction of the region means header/logo, not diagram.
TEXT_DOMINANCE = 0.25
# Caption-like text near a region is a positive diagram signal.
CAPTION_RE = re.compile(r"\b(fig(?:ure)?\.?|diagram|chart)\b", re.I)
# Path-heavy SVGs (text outlined as vectors) are logo art, not diagrams.
# Bytes of SVG per square point of the region; real diagrams are far below this.
MAX_SVG_BYTES_PER_POINT = 80


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


def _nearby_text(region: fitz.Rect, text_blocks: list) -> tuple[float, bool]:
    """Return (overlapping+adjacent text area, whether a caption is nearby)."""
    search = fitz.Rect(region.x0 - NEAR_MARGIN, region.y0 - NEAR_MARGIN,
                       region.x1 + NEAR_MARGIN, region.y1 + NEAR_MARGIN)
    text_area = 0.0
    has_caption = False
    for b in text_blocks:
        bb = fitz.Rect(b["bbox"]) if isinstance(b, dict) else fitz.Rect(b[:4])
        inter = search & bb
        if inter.is_empty:
            continue
        text_area += inter.get_area()
        text = b.get("text", "") if isinstance(b, dict) else ""
        if text and CAPTION_RE.search(text):
            has_caption = True
    return text_area, has_caption


def is_diagram(region: fitz.Rect, text_blocks: list) -> bool:
    """True when the region is a diagram, not cover/header art.

    Cover logos and title art have substantial title or address text beside them.
    Real diagrams do not. A nearby caption is a positive signal and overrides
    moderate text overlap (labeled diagrams).
    """
    region_area = region.get_area()
    if region_area <= 0:
        return False
    text_area, has_caption = _nearby_text(region, text_blocks)
    if has_caption:
        return True
    return (text_area / region_area) < TEXT_DOMINANCE


def is_path_heavy(svg: str, region: fitz.Rect) -> bool:
    """True when the SVG is text outlined as vectors (logo art).

    Real diagrams produce modest SVG for their area. Outlined text produces
    huge path data for a small region. Same cutoff for every page.
    """
    area = region.get_area()
    if area <= 0:
        return True
    return (len(svg) / area) > MAX_SVG_BYTES_PER_POINT
