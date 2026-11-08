"""Basic extraction with PyMuPDF: text blocks in reading order, native vectors or figure renders."""
import pymupdf as fitz
from pathlib import Path
from typing import List, Dict, Any
import json

def extract_page(page: fitz.Page) -> Dict[str, Any]:
    """Extract text blocks (reading order) and detect drawings."""
    # Text blocks with position for rough reading order
    blocks = page.get_text("blocks")  # list of (x0,y0,x1,y1, text, block_no, block_type)
    text_blocks = []
    for b in sorted(blocks, key=lambda x: (x[1], x[0])):  # top-to-bottom, left-to-right
        if b[6] == 0:  # text block
            text_blocks.append({
                "bbox": [b[0], b[1], b[2], b[3]],
                "text": b[4].strip(),
            })

    # Native drawings / vectors
    drawings = page.get_drawings()
    has_vectors = len(drawings) > 0

    # Render page for figure inspection / AI vectorization path
    pix = page.get_pixmap(dpi=150)
    # In real pipeline we would save only diagram regions; here we note the capability

    return {
        "text_blocks": text_blocks,
        "has_native_vectors": has_vectors,
        "drawing_count": len(drawings),
        "width": page.rect.width,
        "height": page.rect.height,
    }

def extract_pdf(pdf_path: Path) -> Dict[str, Any]:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        pages.append(extract_page(page))
    doc.close()
    return {
        "path": str(pdf_path),
        "page_count": len(pages),
        "pages": pages,
    }

def extract_native_svg_stub(page: fitz.Page, out_path: Path) -> str:
    """Placeholder: in real pipeline use page.get_svg_image() or reconstruct from drawings.
    For prototype we note that native vectors exist and can be exported.
    """
    try:
        svg = page.get_svg_image(text_as_path=False)
        out_path.write_text(svg)
        return str(out_path)
    except Exception as e:
        return f"svg_export_failed: {e}"
