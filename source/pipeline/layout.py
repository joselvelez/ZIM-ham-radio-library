"""Reading order — single source of truth.

Gap-based column detection. Finds the vertical gap between columns first,
then assigns each block to the column whose region contains its center.
Left column is emitted fully (top to bottom), then the next column.

This handles TOC and other pages where block bboxes are wide (leader dots)
but block centers still fall cleanly into columns. The official PyMuPDF
column_boxes x-overlap join fails on those pages; gap detection does not.

Fail Fast: raises UnclassifiableLayout when a block center falls in a gap
or when columns cannot be determined on a clearly multi-column page.
"""
from __future__ import annotations
from typing import List, Sequence, Tuple


class UnclassifiableLayout(ValueError):
    """Raised when text blocks cannot be assigned to unique columns."""


# Minimum gap (as a fraction of page width) to treat the page as multi-column.
MIN_GAP_FRACTION = 0.08
# A block center within this fraction of a column edge is ambiguous.
EDGE_TOLERANCE = 0.02


def _as_rect(block: dict) -> tuple[float, float, float, float]:
    bb = block.get("bbox")
    if not bb or len(bb) < 4:
        raise UnclassifiableLayout("block missing bbox")
    return float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])


def _centers(rects: Sequence[tuple]) -> List[float]:
    return [(r[0] + r[2]) / 2 for r in rects]


def _find_gap(centers: List[float], page_width: float) -> Tuple[float, float] | None:
    """Return (gap_start, gap_end) of the largest interior gap, or None.

    A gap is a span with no block centers. The largest gap that is at least
    MIN_GAP_FRACTION of the page width is the column separator.
    """
    if len(centers) < 2:
        return None
    sorted_c = sorted(centers)
    best = None
    best_width = 0.0
    min_gap = page_width * MIN_GAP_FRACTION
    for i in range(len(sorted_c) - 1):
        gap = sorted_c[i + 1] - sorted_c[i]
        if gap > best_width and gap >= min_gap:
            best_width = gap
            best = (sorted_c[i], sorted_c[i + 1])
    return best


def _assign_column(center: float, gap: Tuple[float, float], page_width: float) -> int:
    """Return 0 for left of the gap, 1 for right. Fail Fast on the edge."""
    gap_start, gap_end = gap
    edge = page_width * EDGE_TOLERANCE
    if center <= gap_start:
        return 0
    if center >= gap_end:
        return 1
    # Center falls inside the gap. Ambiguous only if it is near an edge.
    if center - gap_start < edge or gap_end - center < edge:
        raise UnclassifiableLayout(
            f"block center {center:.1f} falls on column gap edge"
        )
    # Deep in the gap — still ambiguous; do not guess.
    raise UnclassifiableLayout(
        f"block center {center:.1f} falls inside column gap"
    )


def column_order(blocks: Sequence[dict], page_width: float) -> List[dict]:
    """Return blocks in reading order.

    Single-column pages are sorted top-to-bottom, left-to-right.
    Multi-column pages are left column fully, then right column.
    Raises UnclassifiableLayout when a block cannot be assigned.
    """
    if not blocks:
        return []
    if page_width <= 0:
        raise UnclassifiableLayout("page_width must be positive")

    items = [dict(b) for b in blocks]
    rects = [_as_rect(b) for b in items]
    centers = _centers(rects)

    gap = _find_gap(centers, page_width)
    if gap is None:
        # Single column: top-to-bottom, then left-to-right.
        order = sorted(range(len(items)), key=lambda i: (rects[i][1], rects[i][0]))
        return [items[i] for i in order]

    left: List[int] = []
    right: List[int] = []
    for i, c in enumerate(centers):
        col = _assign_column(c, gap, page_width)
        (left if col == 0 else right).append(i)

    if not left or not right:
        # Gap found but all blocks landed on one side — treat as single column.
        order = sorted(range(len(items)), key=lambda i: (rects[i][1], rects[i][0]))
        return [items[i] for i in order]

    left.sort(key=lambda i: (rects[i][1], rects[i][0]))
    right.sort(key=lambda i: (rects[i][1], rects[i][0]))
    return [items[i] for i in left + right]
