"""Assemble semantic HTML from pymupdf4llm markdown and PNG figures.

Markdown is converted with the standard `markdown` library. Figures for a
page are placed after that page's HTML. No custom heading or reading-order
logic lives here.
"""
from pathlib import Path
from typing import Dict, Any, List
import html
import re
from datetime import datetime

import markdown as md_lib

from .structure import clean_caption_labels


def _title_from_markdown(chunks: List[dict], fallback: str) -> str:
    """First markdown heading becomes the title."""
    for chunk in chunks:
        for line in chunk.get("text", "").splitlines():
            m = re.match(r"^#{1,6}\s+\**(.+?)\**\s*$", line.strip())
            if m and len(m.group(1)) > 3:
                return m.group(1).strip("* ")
    return fallback


def _caption(page_no: int, labels: List[str]) -> str:
    if page_no is None:
        raise ValueError("figure missing page association")
    base = f"Figure from page {page_no + 1}"
    clean = clean_caption_labels(labels)
    if clean:
        return f"{base}. {' '.join(clean)}"
    return base


def make_article_html(record: Dict[str, Any], extracted: Dict[str, Any], figures: list | None = None) -> str:
    chunks = extracted.get("chunks") or []
    title = _title_from_markdown(chunks, record.get("id", "Untitled"))
    category = record["category"]
    source_pdf = record.get("path", "unknown")
    sha = record.get("sha256", "")[:12]
    slug = record["id"]

    by_page: Dict[int, List[dict]] = {}
    for fig in figures or []:
        if Path(fig["path"]).exists():
            by_page.setdefault(fig["page"], []).append(fig)

    body_parts = []
    for chunk in chunks:
        page_no = (chunk.get("metadata") or {}).get("page")
        # pymupdf4llm page is 1-based
        page_idx = (page_no - 1) if isinstance(page_no, int) else None
        text = chunk.get("text", "").strip()
        if text:
            body_parts.append(md_lib.markdown(text, extensions=["extra", "sane_lists"]))
        if page_idx is not None:
            for fig in by_page.get(page_idx, []):
                rel = f"{slug}/{Path(fig['path']).name}"
                cap = _caption(fig["page"], fig.get("labels") or [])
                body_parts.append(
                    f'<figure><img src="{html.escape(rel)}" alt="{html.escape(cap)}">'
                    f"<figcaption>{html.escape(cap)}</figcaption></figure>"
                )

    meta = (
        f'<meta name="category" content="{html.escape(category)}">\n'
        f'<meta name="source" content="{html.escape(source_pdf)}">\n'
        f'<meta name="sha256" content="{sha}">\n'
        f'<meta name="pipeline" content="pymupdf4llm">\n'
        f'<meta name="generated" content="{datetime.utcnow().isoformat()}Z">'
    )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  {meta}
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; background: #0c121c; color: #e8eef5; line-height: 1.55; }}
    h1, h2, h3, h4, h5, h6 {{ color: #ffdc50; margin-top: 1.6rem; }}
    a {{ color: #64b4ff; }}
    figure {{ margin: 1.5rem 0; background: #1a2230; padding: 1rem; border-radius: 6px; }}
    figure img {{ max-width: 100%; height: auto; background: #fff; }}
    figcaption {{ font-size: 0.85rem; color: #8aa; margin-top: 0.5rem; }}
    .meta {{ font-size: 0.8rem; color: #6a7; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #334; padding: 0.4rem 0.6rem; }}
  </style>
</head>
<body>
  <p><a href="../../index.html">← Back to index</a></p>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Category: {html.escape(category)} · Source: {html.escape(source_pdf)} · SHA: {sha}</p>
  {"".join(body_parts)}
</body>
</html>
'''


def write_article(record: Dict[str, Any], extracted: Dict[str, Any], html_root: Path, figures: list | None = None) -> Path:
    import shutil
    category = record["category"]
    art_dir = html_root / "articles" / category
    art_dir.mkdir(parents=True, exist_ok=True)
    slug = record["id"]
    out = art_dir / f"{slug}.html"
    asset_dir = art_dir / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    figs = [f for f in (figures or []) if Path(f["path"]).exists()]
    out.write_text(make_article_html(record, extracted, figs))
    kept = set()
    for fig in figs:
        path = Path(fig["path"])
        dest = asset_dir / path.name
        shutil.copy(path, dest)
        kept.add(dest.name)
    for leftover in list(asset_dir.glob("*.svg")) + list(asset_dir.glob("*.png")):
        if leftover.name not in kept:
            leftover.unlink()
    for leftover in art_dir.glob(f"{slug}*.svg"):
        leftover.unlink()
    if not any(asset_dir.iterdir()):
        asset_dir.rmdir()
    return out
