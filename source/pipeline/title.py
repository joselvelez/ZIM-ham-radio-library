"""Document title from the largest specific line on the early pages.

The PDF info-dictionary title is untrusted (often a path or a filename).
The first heading is often a generic cover word ("OPERATING MANUAL") that
is the same on every manual of a series. Neither identifies the document.

The title is the largest non-generic text line on the first pages.
Generic cover words are skipped. Fail Fast if nothing specific is found.
"""
from __future__ import annotations
from pathlib import Path

import pymupdf as fitz

# Cover words that appear on many documents and do not identify one.
GENERIC = frozenset({
    "operating manual",
    "manual",
    "introduction",
    "contents",
    "table of contents",
    "specifications",
    "preface",
    "index",
    "warning",
    "caution",
    "notice",
})

# How many early pages to scan. Covers live on page 1; the real title
# often appears as a running header on the next pages.
TITLE_PAGES = 6
MIN_TITLE_LEN = 4


def _lines(page: fitz.Page) -> list[tuple[float, str]]:
    """(font size, text) for every non-empty line on the page."""
    out = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans") or []
            if not spans:
                continue
            size = max(s.get("size", 0) for s in spans)
            text = "".join(s.get("text", "") for s in spans).strip()
            if text:
                out.append((size, text))
    return out


def _specific(text: str) -> bool:
    """A line identifies a document when it is not a generic cover word."""
    cleaned = " ".join(text.split()).strip(" .:-")
    if len(cleaned) < MIN_TITLE_LEN:
        return False
    return cleaned.lower() not in GENERIC


def document_title(pdf_path: Path) -> str:
    """Largest specific line that identifies the document. Fail Fast if none.

    A line that appears on more than one early page is a running title.
    That is preferred over a single large section heading, which is
    specific to a section and not to the document.
    If nothing repeats, the largest specific line is used.
    """
    doc = fitz.open(pdf_path)
    try:
        counts: dict[str, int] = {}
        sizes: dict[str, float] = {}
        for i in range(min(TITLE_PAGES, doc.page_count)):
            seen_on_page = set()
            for size, text in _lines(doc[i]):
                if not _specific(text):
                    continue
                key = " ".join(text.split())
                seen_on_page.add(key)
                sizes[key] = max(sizes.get(key, 0), size)
            for key in seen_on_page:
                counts[key] = counts.get(key, 0) + 1
        if not counts:
            raise SystemExit(
                f"No specific title on the first {TITLE_PAGES} pages of {pdf_path.name}. "
                "The largest lines are generic cover words or too short."
            )
        repeating = [k for k, n in counts.items() if n > 1]
        pool = repeating or list(counts)
        return max(pool, key=lambda k: sizes[k])
    finally:
        doc.close()
