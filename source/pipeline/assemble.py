"""Assemble semantic HTML from pymupdf4llm markdown and figure images.

Markdown is converted with the standard `markdown` library. Figures for a
page are placed after that page's HTML. No custom heading or reading-order
logic lives here.

Figures are separate files in the article's asset directory
(``{slug}/{file}``) and are referenced by relative path, as CONVERSION.md
specifies. zimwriterfs packs them as their own ZIM entries; Kiwix serves
them like any other ZIM image. Images are never inlined as data URIs.
"""
from pathlib import Path
from typing import Dict, Any, List
import html
import re
from datetime import datetime
from urllib.parse import quote

import markdown as md_lib
from bs4 import BeautifulSoup

from .structure import clean_caption_labels
from .toc import toc_to_markdown
from .style import add_heading_ids, link_toc, toc_nav_html, unwrap_key_label_links, wrap_figures, LIGHTBOX_JS, STYLE_CSS


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


def figure_src(slug: str, fig: Dict[str, Any]) -> str:
    """Relative URL of a figure file from its article (same directory level)."""
    return quote(f"{slug}/{Path(fig['path']).name}")


def _size_attrs(fig: Dict[str, Any]) -> Dict[str, str]:
    """width/height so the browser reserves space for lazy-loaded images."""
    w, h = fig.get("width"), fig.get("height")
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        return {"width": str(w), "height": str(h)}
    return {}


def _img_tag(src: str, alt: str, fig: Dict[str, Any], lazy: bool = True) -> str:
    attrs = {"src": src, "alt": alt, **_size_attrs(fig)}
    if lazy:
        attrs["loading"] = "lazy"
    attrs["decoding"] = "async"
    return "<img " + " ".join(f'{k}="{html.escape(v)}"' for k, v in attrs.items()) + ">"


def make_article_html(record: Dict[str, Any], extracted: Dict[str, Any], figures: list | None = None) -> str:
    chunks = extracted.get("chunks") or []
    # Title is resolved before assembly and stored on the record.
    # The first heading is not the title: it is often a generic cover word.
    title = record.get("title")
    if not title:
        raise ValueError("record has no title; title resolution must run before assembly")
    category = record["category"]
    source_pdf = record.get("path", "unknown")
    sha = record.get("sha256", "")[:12]
    slug = record["id"]

    by_page: Dict[int, List[dict]] = {}
    for fig in figures or []:
        if Path(fig["path"]).exists():
            by_page.setdefault(fig["page"], []).append(fig)

    body_parts = []
    for i, chunk in enumerate(chunks):
        meta = chunk.get("metadata") or {}
        page_no = meta.get("page")
        # Layout may omit page. Fall back to chunk order (0-based).
        page_idx = (page_no - 1) if isinstance(page_no, int) else i
        text = toc_to_markdown(chunk.get("text", "")).strip()
        if text:
            body_parts.append(md_lib.markdown(text, extensions=["extra", "sane_lists"]))
        for fig in by_page.get(page_idx, []):
            # Relative path to the sibling asset directory. Not a data URI:
            # NOMAD's extractor only reads text tags (h2-h4, p, lists,
            # tables) and never loads <img>, and Kiwix resolves relative
            # image entries natively. Inlining base64 made articles 30x
            # larger and stored every figure three times in the ZIM.
            img_path = Path(fig["path"])
            if not img_path.exists():
                raise SystemExit(f"Figure file missing at assembly time: {img_path}")
            cap = _caption(fig["page"], fig.get("labels") or [])
            body_parts.append(
                f"<figure>{_img_tag(figure_src(slug, fig), cap, fig)}"
                f"<figcaption>{html.escape(cap)}</figcaption></figure>"
            )

    body_html = "".join(body_parts)
    soup = BeautifulSoup(f"<div id=\"body\">{body_html}</div>", "html.parser")
    unwrap_key_label_links(soup)
    index = add_heading_ids(soup)
    link_toc(soup, index)
    wrap_figures(soup)
    nav = toc_nav_html(soup)
    body = str(soup.find(id="body").decode_contents())

    meta = (
        f'<meta name="title" content="{html.escape(title)}">\n'
        f'<meta name="category" content="{html.escape(category)}">\n'
        f'<meta name="source" content="{html.escape(source_pdf)}">\n'
        f'<meta name="sha256" content="{sha}">\n'
        f'<meta name="pipeline" content="pymupdf4llm">\n'
        f'<meta name="generated" content="{datetime.utcnow().isoformat()}Z">'
    )

    # Back link lives in the fixed sidebar when a TOC exists.
    # Otherwise a sticky bar keeps it visible while scrolling.
    back_in_main = ""
    if not nav:
        back_in_main = '<div class="back-bar"><a href="../../index.html">← Back to index</a></div>\n      '

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
      {back_in_main}<h1>{html.escape(title)}</h1>
      <p class="meta">Category: {html.escape(category)} · Source: {html.escape(source_pdf)} · SHA: {sha}</p>
      {body}
    </main>
  </div>
  <script>{LIGHTBOX_JS}</script>
</body>
</html>
'''


def make_scan_html(record: Dict[str, Any], extracted: Dict[str, Any], figures: list) -> str:
    """A scanned document. Each page image is the content.

    Full width, no sidebar. OCR text sits in a closed block under each
    page so search and the RAG can index it without a wall of noise.
    """
    title = record.get("title")
    if not title:
        raise ValueError("record has no title; title resolution must run before assembly")
    category = record["category"]
    source_pdf = record.get("path", "unknown")
    sha = record.get("sha256", "")[:12]
    slug = record["id"]
    chunks = extracted.get("chunks") or []

    soup = BeautifulSoup('<div id="body"></div>', "html.parser")
    body = soup.find(id="body")
    for i, fig in enumerate(figures):
        page_no = fig.get("page", i) + 1
        figure = soup.new_tag("figure", attrs={"class": "scan-page"})
        img = soup.new_tag("img", attrs={
            "src": figure_src(slug, fig), "alt": f"Page {page_no}",
            **_size_attrs(fig), "loading": "lazy", "decoding": "async",
        })
        figure.append(img)
        cap = soup.new_tag("figcaption")
        cap.string = f"Page {page_no}"
        figure.append(cap)
        body.append(figure)
        text = chunks[i].get("text", "").strip() if i < len(chunks) else ""
        if text:
            details = soup.new_tag("details", attrs={"class": "scan-text"})
            summary = soup.new_tag("summary")
            summary.string = f"Page {page_no} text"
            details.append(summary)
            pre = soup.new_tag("pre")
            pre.string = text
            details.append(pre)
            body.append(details)
    wrap_figures(soup)

    meta = (
        f'<meta name="title" content="{html.escape(title)}">\n'
        f'<meta name="category" content="{html.escape(category)}">\n'
        f'<meta name="source" content="{html.escape(source_pdf)}">\n'
        f'<meta name="sha256" content="{sha}">\n'
        f'<meta name="pipeline" content="scan-ocr">\n'
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
    .scan-page {{ max-width: 90rem; margin: 0 auto; padding: 1.5rem; }}
    .scan-page img {{ width: 100%; height: auto; }}
    .scan-text {{ max-width: 90rem; margin: 0 auto 2rem; padding: 0 1.5rem; }}
    .scan-text pre {{ white-space: pre-wrap; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <div class="scan-page">
    <div class="back-bar"><a href="../../index.html">← Back to index</a></div>
    <h1>{html.escape(title)}</h1>
    <p class="meta">Category: {html.escape(category)} · Source: {html.escape(source_pdf)} · SHA: {sha}</p>
    {str(body.decode_contents())}
  </div>
  <script>{LIGHTBOX_JS}</script>
</body>
</html>
'''


def make_poster_html(record: Dict[str, Any], extracted: Dict[str, Any], page_image: dict) -> str:
    """A one-page chart or poster. The page image is the article.

    Extracted text is placed under the image so search and the RAG can
    index the labels. The page is not reflowed.
    """
    title = record.get("title")
    if not title:
        raise ValueError("record has no title; title resolution must run before assembly")
    category = record["category"]
    source_pdf = record.get("path", "unknown")
    sha = record.get("sha256", "")[:12]
    slug = record["id"]
    text = "\n".join(c.get("text", "") for c in extracted.get("chunks") or []).strip()
    text_html = md_lib.markdown(text, extensions=["extra"]) if text else ""
    soup = BeautifulSoup(
        f'<div id="body"><figure class="poster">'
        f'{_img_tag(figure_src(slug, page_image), title, page_image, lazy=False)}'
        f'<figcaption>{html.escape(title)}</figcaption></figure></div>',
        "html.parser",
    )
    wrap_figures(soup)
    figure = str(soup.find("figure"))

    meta = (
        f'<meta name="title" content="{html.escape(title)}">\n'
        f'<meta name="category" content="{html.escape(category)}">\n'
        f'<meta name="source" content="{html.escape(source_pdf)}">\n'
        f'<meta name="sha256" content="{sha}">\n'
        f'<meta name="pipeline" content="pymupdf4llm-poster">\n'
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
    body {{ background: #fff; }}
    .poster-page {{ max-width: 90rem; margin: 0 auto; padding: 1.5rem; }}
    .poster-page h1 {{ font-size: 2rem; }}
    .poster img {{ width: 100%; height: auto; }}
    .poster-text {{ margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <div class="poster-page">
    <div class="back-bar"><a href="../../index.html">← Back to index</a></div>
    <h1>{html.escape(title)}</h1>
    <p class="meta">Category: {html.escape(category)} · Source: {html.escape(source_pdf)} · SHA: {sha}</p>
    {figure}
    <details class="poster-text">
      <summary>Extracted labels (for search)</summary>
      {text_html}
    </details>
  </div>
  <script>{LIGHTBOX_JS}</script>
</body>
</html>
'''


def retire_other_copies(record: Dict[str, Any], html_root: Path) -> None:
    """Remove every article for this document except the current category.

    A document id has exactly one article. Copies left in other categories
    are deleted. An empty category directory is removed.
    """
    import shutil
    slug = record.get("id")
    category = record.get("category")
    if not slug or not category:
        raise ValueError("cannot retire copies without an id and a category")
    articles = html_root / "articles"
    if not articles.exists():
        return
    for cat_dir in list(articles.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name == category:
            continue
        old_html = cat_dir / f"{slug}.html"
        old_assets = cat_dir / slug
        if old_html.exists():
            old_html.unlink()
        if old_assets.exists():
            shutil.rmtree(old_assets)
        if not any(cat_dir.iterdir()):
            cat_dir.rmdir()


def write_article(record: Dict[str, Any], extracted: Dict[str, Any], html_root: Path, figures: list | None = None, page_image: dict | None = None) -> Path:
    """Write the article HTML and copy its figure files into ``{slug}/``.

    Files in the asset directory that the new HTML does not reference
    (for example PNGs from an older pipeline run) are removed.
    """
    import shutil
    category = record["category"]
    art_dir = html_root / "articles" / category
    art_dir.mkdir(parents=True, exist_ok=True)
    slug = record["id"]
    out = art_dir / f"{slug}.html"
    asset_dir = art_dir / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    if page_image is not None:
        figs = [page_image]
        out.write_text(make_poster_html(record, extracted, page_image))
    elif extracted.get("scan"):
        figs = [f for f in (figures or []) if Path(f["path"]).exists()]
        out.write_text(make_scan_html(record, extracted, figs))
    else:
        figs = [f for f in (figures or []) if Path(f["path"]).exists()]
        out.write_text(make_article_html(record, extracted, figs))
    kept = set()
    for fig in figs:
        path = Path(fig["path"])
        shutil.copy(path, asset_dir / path.name)
        kept.add(path.name)
    for leftover in [p for ext in ("svg", "png", "webp", "jpg") for p in asset_dir.glob(f"*.{ext}")]:
        if leftover.name not in kept:
            leftover.unlink()
    for leftover in art_dir.glob(f"{slug}*.svg"):
        leftover.unlink()
    if not any(asset_dir.iterdir()):
        asset_dir.rmdir()
    return out
