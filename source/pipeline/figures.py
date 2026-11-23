"""Figure geometry — single source of truth.

Figure regions come from page.cluster_drawings() (C-side clustering).
Text whose bbox intersects a region (+ margin) is a label; everything else is body.
SVG is produced by clipping to the region and calling get_svg_image (also C-side).
No Python reconstruction of individual paths.

Classification is structural:
- is_rule: thin page-wide lines
- is_barcode: many full-height thin vertical bars
- is_path_art: few drawing primitives that are almost all fills (outlined logos, title art)
- is_diagram: not dominated by paragraph text

Everything else that is a vector cluster is a diagram.
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
# A text block longer than this is a paragraph, not a diagram label.
PARAGRAPH_CHARS = 80
# An exported SVG with more prose than this is a text page, not a diagram.
MAX_SVG_TEXT_CHARS = 200
def is_rule(region: fitz.Rect) -> bool:
    """A header or footer rule: spans most of the page and is only a few points tall."""
    return region.height < 6 and region.width > 200


def is_barcode(region: fitz.Rect, page: fitz.Page) -> bool:
    """A barcode: many thin vertical bars that each span most of the region height.

    Panel drawings and wiring have thin lines of varying height. A barcode's
    bars are all roughly the full height of the region.
    """
    try:
        items = page.get_drawings()
    except Exception:
        return False
    bars = 0
    for d in items:
        rect = d.get("rect")
        if not rect:
            continue
        r = fitz.Rect(rect)
        if (region & r).is_empty:
            continue
        # thin, and spans most of the region height
        if r.width < 4 and r.height > region.height * 0.7:
            bars += 1
    return bars >= 8


def is_path_art(region: fitz.Rect, page: fitz.Page) -> bool:
    """Decorative path-art: logos and titles outlined as vectors.

    Real diagrams are built from many separate stroke and fill primitives.
    Cover logos and title art are one or a few complex filled paths.
    Reject when the intersecting drawings are few and almost all fills.
    """
    try:
        drawings = page.get_drawings()
    except Exception:
        return False
    items = []
    for d in drawings:
        rect = d.get("rect")
        if not rect:
            continue
        r = fitz.Rect(rect)
        if (region & r).is_empty:
            continue
        items.append(d)
    # Real line drawings have dozens or hundreds of primitives.
    if not items or len(items) > 12:
        return False
    types = [d.get("type", "") for d in items]
    strokes = sum(1 for t in types if t in ("s", "fs"))
    fills = sum(1 for t in types if t == "f")
    # Almost pure fills, almost no strokes → outlined path art, not a diagram.
    return strokes <= 1 and fills >= len(items) * 0.75


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
    """True when the region is a diagram, not a block of body text.

    A paragraph that merely sits next to a diagram does not disqualify it.
    The region is body text only when paragraph text covers most of it.
    """
    region_area = region.get_area()
    if region_area <= 0:
        return False
    paragraph_area = 0.0
    for b in text_blocks:
        text = (b.get("text", "") if isinstance(b, dict) else "").strip()
        if len(text) < PARAGRAPH_CHARS:
            continue
        bb = fitz.Rect(b["bbox"]) if isinstance(b, dict) else fitz.Rect(b[:4])
        inter = region & bb
        if not inter.is_empty:
            paragraph_area += inter.get_area()
    # mostly covered by paragraphs → body text, not a diagram
    if paragraph_area / region_area > 0.5:
        return False
    text_area, has_caption = _nearby_text(region, text_blocks)
    if has_caption:
        return True
    return (text_area / region_area) < TEXT_DOMINANCE


def is_prose_svg(svg: str) -> bool:
    """True when the SVG is mostly body text, not a diagram.

    Counts characters inside text elements. Diagrams have short labels.
    A page of prose dumped into an SVG is not a figure.
    """
    import re
    chunks = re.findall(r"<tspan[^>]*>([^<]*)</tspan>", svg)
    text = "".join(chunks)
    return len(text) > MAX_SVG_TEXT_CHARS
# Color-coded chart/table detection (pages whose meaning depends on vector fill colors).
MIN_FILL_CHROMA = 0.15
MIN_COLOR_SWATCH_AREA = 400.0
MIN_COLOR_CHART_COLORS = 6
MIN_COLOR_CHART_AREA_FRACTION = 0.005


def is_color_coded_page(page: fitz.Page) -> bool:
    """True when the page uses many distinct chromatic vector fills over significant area.

    Catches color-coded charts and tables (e.g. resistor color codes, fiber
    color codes, multi-series charts) whose table/label text exceeds
    TEXT_DOMINANCE in is_diagram() so their vector regions were skipped.
    Neutral grays/whites/blacks and tiny icon details are ignored.
    """
    page_area = page.rect.get_area()
    if page_area <= 0:
        return False
    try:
        drawings = page.get_drawings()
    except Exception:
        return False
    if not drawings:
        return False

    by_color_max: dict[tuple[float, float, float], float] = {}
    by_color_sum: dict[tuple[float, float, float], float] = {}
    for d in drawings:
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        rgb = fill[:3]
        if max(rgb) - min(rgb) < MIN_FILL_CHROMA:
            continue
        rect = d.get("rect")
        if not rect:
            continue
        area = (fitz.Rect(rect) & page.rect).get_area()
        if area <= 0:
            continue
        key = (round(rgb[0], 1), round(rgb[1], 1), round(rgb[2], 1))
        if area > by_color_max.get(key, 0.0):
            by_color_max[key] = area
        by_color_sum[key] = by_color_sum.get(key, 0.0) + area

    significant = [k for k, max_a in by_color_max.items() if max_a >= MIN_COLOR_SWATCH_AREA]
    if len(significant) < MIN_COLOR_CHART_COLORS:
        return False
    total_area = sum(by_color_sum[k] for k in significant)
    return (total_area / page_area) >= MIN_COLOR_CHART_AREA_FRACTION
