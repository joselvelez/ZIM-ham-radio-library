"""Write figure images to disk in a web format. Single source of truth.

Two inputs reach this module:

- A pixmap rendered from a page region (vector diagrams, composites,
  posters, pages that are not one clean image). Encoded as WebP q80.
- An image XObject that already *is* the figure (a photo, a scanned page).
  The original stream is reused instead of re-rendering it:
  JPEG data is kept byte-for-byte; 1-bit scans (CCITT, JBIG2) become
  lossless WebP at their own resolution; other encodings (Flate, JPX) are
  decoded once and written as WebP q80.

This follows what openZIM scrapers do (zimscraperlib ``optimize_image`` with
a WebP preset, mwoffliner ``--webp``) and what pdf2htmlEX / OCRmyPDF do with
existing image streams: keep the original when it is already compact, do not
inflate it to 24-bit PNG. Pillow is used directly; it is the encoder that
zimscraperlib wraps (lossy, ``method=6``).

Quality 80 was measured on this corpus (scan text, antenna patterns, photos,
EMP pages): 39-44 dB PSNR against the old 200 dpi PNGs, no visible
difference at 2x zoom, about a third of the PNG size.
"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageChops, ImageFilter, ImageStat

# WebP settings (zimscraperlib-style lossy WebP, higher quality than its
# default q60 because schematics and scan text need it).
WEBP_QUALITY = 80
WEBP_METHOD = 6
# WebP cannot encode a side longer than this.
WEBP_MAX_SIDE = 16383

# An original image is reused as-is only up to this effective resolution.
# Above it (for example a 600 dpi scan placed on a page) it is downscaled to
# the figure DPI and written as WebP. JPEG originals at or below this are
# kept byte-for-byte.
MAX_ORIGINAL_DPI = 300
# Black-and-white (1-bit) scans are stored losslessly at their own
# resolution up to this DPI; they compress far better than a gray render.
MAX_BILEVEL_DPI = 400

# How closely the original image must match a render of its page region
# before it is trusted as "the figure". Grayscale 0-255, per grid cell of a
# ~96 px thumbnail. A mismatch means the PDF changes the image when drawing
# it (colour space, Decode array, mask, clipping): render the region instead.
_MATCH_SIDE = 96
_MATCH_GRID = 8
_MATCH_CELL_MAX = 16.0
_MATCH_MEAN_MAX = 6.0


def _fail(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f"Image write failed for {path}")


def _flatten(img: Image.Image) -> Image.Image:
    """RGB or L, with any transparency composited onto white (the page)."""
    if img.mode in ("RGB", "L"):
        return img
    if img.mode == "1":
        return img.convert("L")
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def _encode_webp(img: Image.Image, out: Path, lossless: bool = False) -> dict:
    img = _flatten(img)
    if max(img.size) > WEBP_MAX_SIDE:
        img = img.copy()
        img.thumbnail((WEBP_MAX_SIDE, WEBP_MAX_SIDE), Image.LANCZOS)
    if lossless:
        # method 4 is ~25x faster than 6 on page scans for the same size.
        img.save(out, format="WEBP", lossless=True, quality=80, method=4)
    else:
        img.save(out, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    _fail(out)
    return {"path": str(out), "width": img.width, "height": img.height}


def pixmap_to_image(pix: fitz.Pixmap) -> Image.Image:
    """Pillow image from a PyMuPDF pixmap (RGB or gray, alpha dropped)."""
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    mode = "L" if pix.n == 1 else "RGB"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def save_pixmap(pix: fitz.Pixmap, out_base: Path) -> dict:
    """Encode a rendered region as WebP q80. ``out_base`` has no suffix."""
    return _encode_webp(pixmap_to_image(pix), out_base.with_suffix(".webp"))


def render_region(page: fitz.Page, clip: fitz.Rect, out_base: Path, dpi: int) -> dict:
    """Render a page region at ``dpi`` and write it as WebP."""
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    info = save_pixmap(pix, out_base)
    info["source"] = "render"
    return info


def _matches_render(page: fitz.Page, region: fitz.Rect, original: Image.Image) -> bool:
    """True when the original image looks like what the page shows there.

    Compares a small render of the region with the original image scaled to
    the same size (both box-filtered and lightly blurred so half-pixel
    offsets and anti-aliasing do not count), cell by cell. This is the guard
    that keeps extract_image from replacing a figure whose colour space,
    Decode array, mask, or clipping changes what is drawn.
    Calibrated on this corpus: true matches score mean <= 4.1, worst cell
    <= 11.2; inverted images score > 100.
    """
    zoom = 2 * _MATCH_SIDE / max(region.width, region.height, 1.0)
    pix = page.get_pixmap(clip=region, matrix=fitz.Matrix(zoom, zoom))
    rendered = pixmap_to_image(pix).convert("L")
    w, h = max(1, round(rendered.width / 2)), max(1, round(rendered.height / 2))
    if min(w, h) < _MATCH_GRID:
        return False
    blur = ImageFilter.BoxBlur(1)
    rendered = rendered.resize((w, h), Image.BOX).filter(blur)
    orig = original.convert("L").resize((w, h), Image.BOX).filter(blur)
    diff = ImageChops.difference(rendered, orig)
    cells = []
    for gy in range(_MATCH_GRID):
        for gx in range(_MATCH_GRID):
            box = (gx * w // _MATCH_GRID, gy * h // _MATCH_GRID,
                   (gx + 1) * w // _MATCH_GRID, (gy + 1) * h // _MATCH_GRID)
            cells.append(ImageStat.Stat(diff.crop(box)).mean[0])
    return sum(cells) / len(cells) <= _MATCH_MEAN_MAX and max(cells) <= _MATCH_CELL_MAX


def _is_upright(transform) -> bool:
    """Image drawn axis-aligned, not flipped or rotated (in unrotated page space)."""
    if not transform or len(transform) < 4:
        return False
    a, b, c, d = transform[:4]
    scale = max(abs(a), abs(d), 1e-6)
    return a > 0 and d > 0 and abs(b) / scale < 1e-3 and abs(c) / scale < 1e-3


def _region_has_overlays(page: fitz.Page, region: fitz.Rect, xref: int) -> bool:
    """True when anything visible is painted inside the image area.

    Another image, a vector path (callout, arrow, label box), or visible
    text inside the region means the figure is a composite and must be
    rendered. Shapes that enclose the whole image (page backgrounds,
    frames) and invisible OCR text are ignored.
    """
    inner = fitz.Rect(region.x0 + 3, region.y0 + 3, region.x1 - 3, region.y1 - 3)
    if inner.is_empty:
        return True
    area = inner.get_area()
    for info in page.get_image_info(xrefs=True) or []:
        if info.get("xref") == xref:
            continue
        inter = fitz.Rect(info.get("bbox") or (0, 0, 0, 0)) & inner
        if not inter.is_empty and inter.get_area() / area > 0.002:
            return True
    for d in page.get_drawings():
        r = fitz.Rect(d.get("rect") or (0, 0, 0, 0))
        if r.contains(inner):
            continue  # background or frame around the image
        # Overlap by coordinates so zero-height rules and arrows count.
        x0, y0 = max(r.x0, inner.x0), max(r.y0, inner.y0)
        x1, y1 = min(r.x1, inner.x1), min(r.y1, inner.y1)
        if x0 <= x1 and y0 <= y1 and max(x1 - x0, y1 - y0) > 2:
            return True
    for span in page.get_texttrace():
        if span.get("type") == 3 or span.get("opacity", 1) == 0:
            continue  # invisible OCR layer
        b = fitz.Rect(span.get("bbox") or (0, 0, 0, 0))
        inter = b & inner
        if not inter.is_empty and inter.get_area() > 0.5 * max(b.get_area(), 1e-6):
            return True
    return False


_TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,   # /Rotate is clockwise; PIL's are counter-clockwise
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def extract_original(page: fitz.Page, xref: int, region: fitz.Rect,
                     out_base: Path, dpi: int, transform=None) -> dict | None:
    """Reuse the image XObject when it is the whole figure. None otherwise.

    ``region`` and ``transform`` come from get_image_info (unrotated page
    space). None means "render the region instead". That happens for images
    drawn flipped, rotated or skewed, soft masks, composites (labels,
    vectors, other images on top), CMYK or unusual JPEGs, images that run
    off the page, and whenever the original does not look like the render
    (colour space such as Separation, Decode array, clipping).

    On a rotated page (/Rotate 90/180/270, common for scans) the image is
    turned losslessly to match what the reader sees; a JPEG is then
    re-encoded instead of kept byte-for-byte.
    """
    rot = page.rotation % 360
    if not xref or rot not in (0, 90, 180, 270) or not _is_upright(transform):
        return None
    visual = region * page.rotation_matrix if rot else fitz.Rect(region)
    on_page = visual & page.rect
    if on_page.is_empty or on_page.get_area() < 0.98 * visual.get_area():
        return None
    doc = page.parent
    try:
        meta = doc.extract_image(xref)
    except Exception:
        return None
    if not meta or not meta.get("image") or meta.get("smask"):
        return None
    try:
        if _region_has_overlays(page, region, xref):
            return None
    except Exception:
        return None

    ext = (meta.get("ext") or "").lower()
    data = meta["image"]
    is_jpeg = ext in ("jpg", "jpeg") and meta.get("colorspace") in (1, 3)
    try:
        if is_jpeg:
            img = Image.open(io.BytesIO(data))
            img.load()
            if img.mode not in ("L", "RGB"):
                return None
        else:
            img = pixmap_to_image(fitz.Pixmap(doc, xref))
        if rot:
            img = img.transpose(_TRANSPOSE[rot])
            is_jpeg = False
        if not _matches_render(page, on_page, img):
            return None
    except Exception:
        return None

    # Effective resolution of the image as placed on the page.
    eff_dpi = max(img.width / (max(visual.width, 1.0) / 72.0),
                  img.height / (max(visual.height, 1.0) / 72.0))

    if is_jpeg and eff_dpi <= MAX_ORIGINAL_DPI * 1.02:
        out = out_base.with_suffix(".jpg")
        out.write_bytes(data)
        _fail(out)
        return {"path": str(out), "width": img.width, "height": img.height,
                "source": "original-jpeg"}

    if meta.get("bpc") == 1 and img.mode == "L" and eff_dpi <= MAX_BILEVEL_DPI * 1.02:
        # Black-and-white scan (CCITT, JBIG2, 1-bit Flate). Lossless WebP at
        # the scan's own resolution is exact and smaller than a lossy 200 dpi
        # render (OCRmyPDF's rule: keep bitonal pages bitonal).
        info = _encode_webp(img, out_base.with_suffix(".webp"), lossless=True)
        info["source"] = "original-bilevel"
        return info

    if eff_dpi > MAX_ORIGINAL_DPI * 1.02:
        ratio = dpi / eff_dpi
        img = _flatten(img)
        img = img.resize((max(1, round(img.width * ratio)), max(1, round(img.height * ratio))),
                         Image.LANCZOS)
    info = _encode_webp(img, out_base.with_suffix(".webp"))
    info["source"] = "original"
    return info
