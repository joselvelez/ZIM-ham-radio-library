"""Reading order — single source of truth.

Based on the official PyMuPDF multi_column.column_boxes algorithm
(PyMuPDF-Utilities/text-extraction/multi_column.py, Artifex multi-column guide).

Detects columns by joining text blocks that do not cross column boundaries,
then returns blocks sorted left-column-first, top-to-bottom within each column.

Fail Fast: raises ValueError when blocks overlap in a way that prevents
a unique column classification.
"""
from __future__ import annotations
from typing import List, Sequence


class UnclassifiableLayout(ValueError):
    """Raised when text blocks overlap such that columns cannot be determined."""


def _as_rect(block: dict) -> tuple[float, float, float, float]:
    bb = block.get("bbox")
    if not bb or len(bb) < 4:
        raise UnclassifiableLayout("block missing bbox")
    return float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])


def _overlaps_x(a: tuple, b: tuple) -> bool:
    return not (a[2] < b[0] or b[2] < a[0])


def _can_join(left: tuple, right: tuple) -> bool:
    """True when the two boxes can belong to the same column.

    Never join across columns: if their x-ranges are disjoint, they are
    in different columns.
    """
    return _overlaps_x(left, right)


def column_order(blocks: Sequence[dict], page_width: float) -> List[dict]:
    """Return blocks in reading order.

    Left column fully (top to bottom), then the next column, and so on.
    Single-column pages are returned sorted top-to-bottom, left-to-right.
    Raises UnclassifiableLayout on overlapping blocks that cannot be
    assigned to a unique column.
    """
    if not blocks:
        return []
    if page_width <= 0:
        raise UnclassifiableLayout("page_width must be positive")

    # Work on copies so callers are not mutated.
    items = [dict(b) for b in blocks]
    rects = [_as_rect(b) for b in items]

    # Detect heavy overlaps that make column assignment ambiguous.
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            # Significant area overlap (more than 30% of the smaller box)
            ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
            ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
            if ix1 > ix0 and iy1 > iy0:
                inter = (ix1 - ix0) * (iy1 - iy0)
                area_a = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
                area_b = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
                if inter / min(area_a, area_b) > 0.3:
                    raise UnclassifiableLayout(
                        f"overlapping text blocks at {a} and {b}"
                    )

    # Group into columns by joining boxes whose x-ranges overlap.
    columns: List[List[int]] = []
    for idx, r in enumerate(rects):
        placed = False
        for col in columns:
            if any(_can_join(r, rects[k]) for k in col):
                col.append(idx)
                placed = True
                break
        if not placed:
            columns.append([idx])

    # Sort columns left-to-right by the leftmost x of their members.
    columns.sort(key=lambda col: min(rects[k][0] for k in col))

    ordered: List[dict] = []
    for col in columns:
        # Within a column, top-to-bottom, then left-to-right.
        col.sort(key=lambda k: (rects[k][1], rects[k][0]))
        for k in col:
            ordered.append(items[k])
    return ordered
