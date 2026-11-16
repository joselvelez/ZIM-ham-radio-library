"""Extract text via pymupdf4llm (with layout) and figures as high-DPI PNG.

Body text, headings, reading order, and tables come from pymupdf4llm with
the pymupdf-layout engine activated. That is the maintained path; we do not
reimplement layout or table detection.

Figures are clipped regions rasterized at high DPI. Clipped SVG from
get_svg_image is incomplete (MuPDF maintainer guidance); a pixmap of the
region is the usable output.
"""
from __future__ import annotations
import pymupdf as fitz
# Layout must be imported and activated before pymupdf4llm.
import pymupdf.layout
pymupdf.layout.activate()
import pymupdf4llm
from pathlib import Path
from typing import Dict, Any, List

from .figures import figure_regions, is_diagram, is_rule, is_barcode, is_path_art

# Strip repeating page chrome. pymupdf4llm applies these as margins.
PAGE_MARGINS = (0, 50, 0, 50)
FIGURE_DPI = 200


def is_scan(pdf_path: Path) -> bool:
    """True when the early pages have no text layer. A scan, not a reflowable PDF."""
    doc = fitz.open(pdf_path)
    try:
        for i in range(min(6, doc.page_count)):
            if doc[i].get_text().strip():
                return False
        return True
    finally:
        doc.close()


def is_page_image_document(pdf_path: Path) -> bool:
    """True when the document is dominated by full-page images.

    Examines every page. A page counts when a single image covers at least
    85% of its area. The document counts when at least 80% of its pages
    meet that test.

    This catches scanned manuals that also carry an OCR text layer (so
    is_scan returns False) without being fooled by a cover page, a TOC,
    or a few large figures in an otherwise reflowable PDF.
    """
    doc = fitz.open(pdf_path)
    try:
        total = doc.page_count
        if total == 0:
            return False
        hits = 0
        for page in doc:
            area = page.rect.width * page.rect.height
            if area <= 0:
                continue
            for info in page.get_image_info():
                b = info.get("bbox") or (0, 0, 0, 0)
                ia = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
                if ia / area >= 0.85:
                    hits += 1
                    break
        return hits / total >= 0.80
    finally:
        doc.close()


def _require_tessdata() -> None:
    """Fail Fast with the install command if Tesseract language data is missing."""
    import shutil
    if shutil.which("tesseract") is None:
        raise SystemExit(
            "This is a scan. OCR needs Tesseract.\n"
            "  macOS: brew install tesseract\n"
            "Then re-run this file with --force."
        )
    try:
        page = fitz.open()  # not used; probe via a known tessdata path
    except Exception:
        pass
    candidates = [
        Path("/opt/homebrew/share/tessdata/eng.traineddata"),
        Path("/usr/local/share/tessdata/eng.traineddata"),
        Path("/usr/share/tesseract-ocr/5/tessdata/eng.traineddata"),
        Path("/usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata"),
    ]
    if not any(p.exists() for p in candidates):
        raise SystemExit(
            "This is a scan. Tesseract is installed but the English language data is missing.\n"
            "  macOS: brew install tesseract\n"
            "Then re-run this file with --force."
        )


def extract_scan(pdf_path: Path, out_dir: Path, stem: str, max_pages: int | None = None) -> Dict[str, Any]:
    """A scanned or page-image document. Each page is rendered as a PNG.

    Prefer the existing text layer when it is present (OCR already done by
    the producer). Fall back to Tesseract OCR only when a page has no text.
    Fail Fast if OCR is required and Tesseract language data is missing.
    """
    doc = fitz.open(pdf_path)
    total = doc.page_count
    limit = total if max_pages is None else min(max_pages, total)
    chunks = []
    figures = []
    needs_ocr = False
    print(f"Scan: rendering {limit} pages...")
    for i in range(limit):
        if i == 0 or (i + 1) % 10 == 0 or i + 1 == limit:
            print(f"  page {i + 1}/{limit}")
        page = doc[i]
        image = render_page_png(page, out_dir, f"{stem}-page{i}")
        figures.append(image)
        text = page.get_text().strip()
        if not text:
            if not needs_ocr:
                _require_tessdata()
                needs_ocr = True
            try:
                text = page.get_textpage_ocr(language="eng").extractText().strip()
            except Exception as exc:
                doc.close()
                raise SystemExit(f"OCR failed on page {i + 1} of {pdf_path.name}: {exc}")
        chunks.append({"text": text, "metadata": {"page": i + 1}})
    doc.close()
    return {
        "path": str(pdf_path),
        "page_count": total,
        "pages_extracted": len(chunks),
        "chunks": chunks,
        "figures": figures,
        "scan": True,
    }
def is_poster(page_count: int) -> bool:
    """True when the document is one page. Reflow would destroy it."""
    return page_count == 1


def render_page_png(page: fitz.Page, out_dir: Path, stem: str) -> dict:
    """High-DPI render of the whole page. Fail Fast if the write fails."""
    pix = page.get_pixmap(dpi=FIGURE_DPI)
    out = out_dir / f"{stem}-page.png"
    pix.save(str(out))
    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"Page PNG write failed for {out}")
    return {"path": str(out), "page": page.number, "labels": []}


def extract_pdf(pdf_path: Path, max_pages: int | None = None) -> Dict[str, Any]:
    """Extract the document as per-page markdown chunks.

    Default is the full document. max_pages is an explicit debug limit only.
    Fail Fast if pymupdf4llm returns no text.
    """
    doc = fitz.open(pdf_path)
    total = doc.page_count
    doc.close()
    if max_pages is not None and max_pages < 1:
        raise SystemExit("--pages must be a positive integer")
    pages = list(range(total if max_pages is None else min(max_pages, total)))
    if max_pages is not None and len(pages) < total:
        print(f"  [debug] limiting extraction to {len(pages)} of {total} pages")

    chunks = pymupdf4llm.to_markdown(
        str(pdf_path),
        pages=pages,
        page_chunks=True,
        margins=PAGE_MARGINS,
        header=False,
        footer=False,
    )
    if not chunks:
        raise SystemExit(f"pymupdf4llm returned no pages for {pdf_path.name}")
    text = "\n".join(c.get("text", "") for c in chunks)
    if not text.strip():
        raise SystemExit(f"pymupdf4llm returned empty text for {pdf_path.name}")

    return {
        "path": str(pdf_path),
        "page_count": total,
        "pages_extracted": len(chunks),
        "chunks": chunks,
    }


def extract_diagram_pngs(page: fitz.Page, out_dir: Path, stem: str) -> list[dict]:
    """High-DPI PNG of every diagram region on the page.

    Rejects rules, barcodes, path-art, and body text. One PNG per region.
    Fail Fast if a pixmap cannot be written.
    """
    regions = figure_regions(page)
    if not regions:
        return []
    raw = page.get_text("blocks")
    text_blocks = [{"bbox": b[:4], "text": (b[4] or "").strip()}
                   for b in raw if b[6] == 0]
    diagrams = [r for r in regions
                if not is_rule(r)
                and not is_barcode(r, page)
                and not is_path_art(r, page)
                and is_diagram(r, text_blocks)]
    if not diagrams:
        return []
    written: list[dict] = []
    for n, region in enumerate(sorted(diagrams, key=lambda r: (r.y0, r.x0))):
        clip = fitz.Rect(region.x0 - 4, region.y0 - 4, region.x1 + 4, region.y1 + 4) & page.rect
        pix = page.get_pixmap(clip=clip, dpi=FIGURE_DPI)
        out = out_dir / f"{stem}-{n}.png"
        pix.save(str(out))
        if not out.exists() or out.stat().st_size == 0:
            raise SystemExit(f"PNG write failed for {out}")
        labels = []
        for tb in text_blocks:
            bb = fitz.Rect(tb["bbox"])
            if not (region & bb).is_empty and tb["text"]:
                labels.append(tb["text"])
        written.append({
            "path": str(out),
            "page": page.number,
            "bbox": [region.x0, region.y0, region.x1, region.y1],
            "labels": labels,
        })
    return written


# Minimum area fraction of the page for an embedded image to be treated as a figure.
# Filters out tiny icons, logos, and decorative marks.
MIN_RASTER_AREA_FRACTION = 0.02
# Minimum pixel area (width * height) to ignore low-res decorative images.
MIN_RASTER_PIXELS = 40_000


def extract_raster_figures(page: fitz.Page, out_dir: Path, stem: str, existing_regions: list | None = None) -> list[dict]:
    """Extract significant embedded raster images as PNG figures.

    Complements vector-cluster diagrams. Many manuals store schematics,
    panel drawings, and charts as embedded images rather than pure vectors.
    Skips images that substantially overlap an already-accepted vector region.
    Fail Fast if a pixmap cannot be written.
    """
    existing = existing_regions or []
    written: list[dict] = []
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return written

    infos = page.get_image_info(xrefs=True) or []
    for n, info in enumerate(infos):
        bbox = info.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        region = fitz.Rect(bbox)
        if region.is_empty or region.width < 20 or region.height < 12:
            continue
        area = region.get_area()
        if area / page_area < MIN_RASTER_AREA_FRACTION:
            continue
        w = info.get("width") or 0
        h = info.get("height") or 0
        if w * h < MIN_RASTER_PIXELS:
            continue
        # Skip if this image substantially overlaps an already-accepted vector diagram
        if any(not (region & fitz.Rect(r)).is_empty and
               (region & fitz.Rect(r)).get_area() / area > 0.6 for r in existing):
            continue
        # get_image_info bbox is in unrotated space on rotated pages.
        # page.get_pixmap(clip=) expects visual (rotated) coordinates.
        # Transform with the page rotation matrix so the clip matches the page.
        # This is the pattern from PyMuPDF discussions #1721 and the maintainer.
        visual = region * page.rotation_matrix if page.rotation else region
        visual = visual & page.rect
        if visual.is_empty or visual.width < 10 or visual.height < 10:
            continue
        # Small pad so anti-aliased edges are not clipped.
        clip = (visual + (-2, -2, 2, 2)) & page.rect
        pix = page.get_pixmap(clip=clip, dpi=FIGURE_DPI)
        out = out_dir / f"{stem}-raster{n}.png"
        pix.save(str(out))
        if not out.exists() or out.stat().st_size == 0:
            raise SystemExit(f"PNG write failed for {out}")
        written.append({
            "path": str(out),
            "page": page.number,
            "bbox": [region.x0, region.y0, region.x1, region.y1],
            "labels": [],
            "kind": "raster",
        })
    return written
