"""Document structure — single source of truth.

Classifies text blocks by font size (IdentifyHeaders pattern from
PyMuPDF4LLM), drops repeating page chrome, dehyphenates broken words,
and rejects button-cluster captions.

Fail Fast: raises NoBodyFont if the body font size cannot be determined.
"""
from __future__ import annotations
import re
from collections import Counter
from typing import List, Sequence


class NoBodyFont(ValueError):
    """Raised when the document has no dominant body font size."""


# Body is the most common size. Headings are larger; chrome is the
# page-number / running-title size that repeats in the margins.
HEADING_RATIO = 1.10   # ≥ this × body → heading
SECTION_RATIO = 1.5    # ≥ this × body → h2, else h3
MARGIN = 60            # points from top/bottom treated as chrome band
MAX_CAPTION_CHARS = 40


def body_font_size(sizes: Sequence[float]) -> float:
    """Return the most common font size. Fail Fast if none."""
    if not sizes:
        raise NoBodyFont("no font sizes in document")
    counts = Counter(round(s, 1) for s in sizes)
    size, _ = counts.most_common(1)[0]
    if size <= 0:
        raise NoBodyFont(f"invalid body font size {size}")
    return size


def role_for_size(size: float, body: float) -> str:
    """Return 'h2', 'h3', or 'body' from font size relative to body."""
    if size >= body * SECTION_RATIO:
        return "h2"
    if size >= body * HEADING_RATIO:
        return "h3"
    return "body"


def is_page_chrome(text: str, size: float, y0: float, y1: float, page_height: float, body: float) -> bool:
    """True for repeating page headers, footers, and bare page numbers.

    Page chrome is short text in the top or bottom margin, or text at the
    page-number size that matches a page number or the running title.
    """
    t = text.strip()
    if not t:
        return True
    in_margin = y0 < MARGIN or y1 > page_height - MARGIN
    # Bare page number
    if re.fullmatch(r"\d{1,3}", t):
        return True
    # Running title at header size, in the margin
    if in_margin and size > body and len(t) < 60:
        return True
    # Known running title pattern
    if re.search(r"operating manual", t, re.I) and in_margin:
        return True
    return False


def dehyphenate(text: str) -> str:
    """Join words broken across lines with a trailing hyphen.

    'charg-\ning' → 'charging'. Does not touch hyphens that are not at
    a line end.
    """
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def is_button_cluster(text: str) -> bool:
    """True when the text is a run of short uppercase tokens (button labels).

    Real captions have mixed case or longer words. Button clusters are
    things like 'HOME CLAR' or 'BAND DWN UP TX/BUSY'.
    """
    t = " ".join(text.split())
    if not t or len(t) > MAX_CAPTION_CHARS:
        return True
    tokens = t.split()
    if len(tokens) < 2:
        return False
    upper = sum(1 for tok in tokens if tok.isupper() and len(tok) <= 6)
    return upper >= len(tokens) * 0.6


def clean_caption_labels(labels: Sequence[str]) -> List[str]:
    """Keep at most two short, non-button labels."""
    out = []
    for lbl in labels:
        if not lbl:
            continue
        text = " ".join(lbl.split())
        if not text or is_button_cluster(text):
            continue
        out.append(text)
        if len(out) == 2:
            break
    return out
