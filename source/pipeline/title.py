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


def variant_qualifier(pdf_path: Path) -> str:
    """The part of the filename that distinguishes a variant.

    Band charts of the same title differ by color and size:
    hambands4_bw_11x8_5 vs hambands4_color_11x8_5.
    Those tokens are the qualifier. Empty when the filename has none.
    """
    stem = pdf_path.stem.lower()
    tokens = []
    for token in ("color", "bw", "grayscale", "grey", "mono"):
        if token in stem:
            tokens.append(token)
    for part in stem.replace("-", "_").split("_"):
        if "x" in part and any(c.isdigit() for c in part):
            tokens.append(part.replace("_", "."))
    return ", ".join(tokens)


def disambiguate(base: str, qualifier: str) -> str:
    """Append the qualifier when the base title is shared. Fail Fast if empty."""
    if not qualifier:
        raise ValueError(f"title {base!r} collides and the filename has no variant")
    return f"{base} ({qualifier})"


def _has_text(doc: fitz.Document) -> bool:
    """True if any of the early pages has a text layer."""
    for i in range(min(TITLE_PAGES, doc.page_count)):
        if doc[i].get_text().strip():
            return True
    return False


def _ocr_lines(page: fitz.Page) -> list[str]:
    """OCR one page. Empty if Tesseract data is not installed."""
    try:
        text = page.get_textpage_ocr(language="eng").extractText()
    except Exception:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _filename_title(pdf_path: Path) -> str:
    """A readable title from the filename when the scan cannot be read."""
    stem = pdf_path.stem
    parts = stem.split("_")
    # Drop the nav-comms_<prefix> triage prefix.
    rest = parts[2:] if len(parts) >= 3 and parts[0] == "nav-comms" else parts
    words = " ".join(rest).replace("-", " ").replace("_", " ")
    return " ".join(w.capitalize() for w in words.split())


def _title_from_ocr(doc: fitz.Document, pdf_path: Path) -> str:
    """Title from the cover of a scan. Filename if OCR is unavailable."""
    lines: list[str] = []
    for i in range(min(TITLE_PAGES, doc.page_count)):
        lines.extend(_ocr_lines(doc[i]))
        if lines:
            break
    specific = [" ".join(ln.split()) for ln in lines if _specific(ln)]
    # A cover OCR line is a title only when it is a real phrase.
    # Short OCR noise ("Skywave aed") is rejected.
    usable = [ln for ln in specific if len(ln) >= 20 and len(ln.split()) >= 3]
    if usable:
        return max(usable, key=len)
    print(f"  OCR found no usable title for {pdf_path.name}; using the filename")
    return _filename_title(pdf_path)


def document_title(pdf_path: Path) -> str:
    """Largest specific line that identifies the document.

    A line that appears on more than one early page is a running title.
    That is preferred over a single large section heading.
    A scan with no text layer is OCR'd. If OCR is unavailable, the
    filename is the title. A text PDF with only generic cover words
    still stops.
    """
    doc = fitz.open(pdf_path)
    try:
        if not _has_text(doc):
            return _title_from_ocr(doc, pdf_path)
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
