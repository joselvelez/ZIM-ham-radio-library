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
from bs4 import BeautifulSoup

from .structure import clean_caption_labels
from .toc import toc_to_markdown
from .style import add_heading_ids, link_toc, toc_nav_html, wrap_figures, LIGHTBOX_JS, STYLE_CSS


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
        text = toc_to_markdown(chunk.get("text", "")).strip()
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

    body_html = "".join(body_parts)
    soup = BeautifulSoup(f"<div id=\"body\">{body_html}</div>", "html.parser")
    index = add_heading_ids(soup)
    link_toc(soup, index)
    wrap_figures(soup)
    nav = toc_nav_html(soup)
    body = str(soup.find(id="body").decode_contents())

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
    {STYLE_CSS}
  </style>
</head>
<body>
  <div class="layout">
    {nav}
    <main>
      <p><a href="../../index.html">← Back to index</a></p>
      <h1>{html.escape(title)}</h1>
      <p class="meta">Category: {html.escape(category)} · Source: {html.escape(source_pdf)} · SHA: {sha}</p>
      {body}
    </main>
  </div>
  <script>{LIGHTBOX_JS}</script>
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
