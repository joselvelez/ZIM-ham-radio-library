"""Article style layer — single source of truth.

Post-processes the assembled HTML so it matches what mature documentation
readers do (mdBook, MkDocs):

- Stable ids on headings
- TOC list items become links to those ids
- Fixed sidebar nav (Back to index + Contents) that always stays visible
- Sticky back bar for pages without a TOC
- Figures open in a native dialog lightbox

No external CSS or JS. Body text stays in the main flow so Kiwix and the
NOMAD extractor still see the full article.
"""
from __future__ import annotations
import html
import re
from typing import Dict, List

from bs4 import BeautifulSoup


_SLUG = re.compile(r"[^a-z0-9]+")
_TOC_ITEM = re.compile(r"^(.+?)\s+[—–-]\s+\d{1,3}\s*$")


def slugify(text: str) -> str:
    s = _SLUG.sub("-", text.lower()).strip("-")
    return s or "section"


def add_heading_ids(soup: BeautifulSoup) -> Dict[str, str]:
    """Assign a unique id to every heading. Returns title -> id.

    A heading with no text is not a heading. OCR noise produces these.
    It is removed. A heading that has text always gets an id.
    """
    seen: Dict[str, int] = {}
    index: Dict[str, str] = {}
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            tag.decompose()
            continue
        base = slugify(text)
        n = seen.get(base, 0)
        seen[base] = n + 1
        hid = base if n == 0 else f"{base}-{n + 1}"
        tag["id"] = hid
        # First occurrence wins for TOC matching.
        index.setdefault(text.lower(), hid)
    return index


def link_toc(soup: BeautifulSoup, index: Dict[str, str]) -> int:
    """Turn TOC list items into links. Returns how many were linked.

    A TOC item is 'Title — page'. The title must match a heading.
    Items that do not match are left as text (they are body lists).
    """
    linked = 0
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        m = _TOC_ITEM.match(text)
        if not m:
            continue
        title = m.group(1).strip()
        hid = index.get(title.lower())
        if not hid:
            continue
        a = soup.new_tag("a", href=f"#{hid}")
        a.string = text
        li.clear()
        li.append(a)
        linked += 1
    return linked


def toc_nav_html(soup: BeautifulSoup) -> str:
    """Sidebar nav from the list with the most TOC links.

    Includes the always-visible Back to index link at the top of the fixed sidebar.
    """
    best = None
    best_links = []
    for ul in soup.find_all("ul"):
        links = ul.find_all("a", href=re.compile(r"^#"))
        if len(links) > len(best_links):
            best = ul
            best_links = links
    if len(best_links) < 3:
        return ""
    items = [
        f'<li><a href="{html.escape(a["href"])}">{html.escape(a.get_text())}</a></li>'
        for a in best_links
    ]
    back = '<p class="back"><a href="../../index.html">← Back to index</a></p>'
    return (
        '<nav class="toc" aria-label="Contents">'
        + back
        + '<p class="toc-title">Contents</p>'
        + f"<ul>{''.join(items)}</ul></nav>"
    )


def wrap_figures(soup: BeautifulSoup) -> int:
    """Make each figure open a native dialog. Returns how many were wrapped.

    The image stays in the main flow. The dialog reuses the same src.
    """
    count = 0
    for fig in soup.find_all("figure"):
        img = fig.find("img")
        if not img or not img.get("src"):
            continue
        dlg_id = f"fig-{count + 1}"
        cap = fig.find("figcaption")
        caption = cap.get_text(" ", strip=True) if cap else ""
        btn = soup.new_tag("button", type="button", **{
            "class": "zoom",
            "data-dialog": dlg_id,
            "aria-label": f"Enlarge {caption}" if caption else "Enlarge figure",
        })
        img.replace_with(btn)
        btn.append(img)
        dlg = soup.new_tag("dialog", id=dlg_id)
        big = soup.new_tag("img", src=img["src"], alt=img.get("alt", ""))
        dlg.append(big)
        if caption:
            p = soup.new_tag("p")
            p.string = caption
            dlg.append(p)
        close = soup.new_tag("form", method="dialog")
        cbtn = soup.new_tag("button")
        cbtn.string = "Close"
        close.append(cbtn)
        dlg.append(close)
        fig.append(dlg)
        count += 1
    return count


# Minimal script: open the dialog for the clicked figure. No library.
LIGHTBOX_JS = """
document.querySelectorAll('button.zoom').forEach(function (b) {
  b.addEventListener('click', function () {
    var d = document.getElementById(b.getAttribute('data-dialog'));
    if (d && d.showModal) d.showModal();
  });
});
""".strip()


STYLE_CSS = """
:root { color-scheme: light; }
body { font-family: system-ui, sans-serif; margin: 0; background: #fff; color: #1a1a1a; line-height: 1.6; }
.layout { display: block; max-width: none; margin: 0; padding: 0; }
/* Fixed sidebar: Back to index + Contents always stay visible */
nav.toc {
  position: fixed;
  top: 0;
  left: 0;
  width: 16rem;
  height: 100vh;
  overflow-y: auto;
  z-index: 100;
  background: #fff;
  border-right: 1px solid #ddd;
  padding: 1rem 0.75rem;
  box-sizing: border-box;
  font-size: 0.85rem;
}
nav.toc .back { margin: 0 0 0.75rem; font-weight: 600; font-size: 0.95rem; }
nav.toc .back a { color: #0b57d0; text-decoration: none; }
nav.toc .back a:hover { text-decoration: underline; }
nav.toc .toc-title { color: #1a1a1a; font-weight: 600; margin: 0 0 0.5rem; }
nav.toc ul { list-style: none; padding: 0; margin: 0; }
nav.toc li { margin: 0.25rem 0; }
nav.toc a { color: #0b57d0; text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }
/* Main content shifted right of the fixed sidebar */
.layout:has(nav.toc) main {
  margin-left: 16rem;
  padding: 1.5rem 2rem;
  max-width: calc(100vw - 16rem);
  min-width: 0;
  overflow-x: auto;
  box-sizing: border-box;
}
/* Sticky back bar for pages without a TOC (scans, posters) */
.back-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #fff;
  padding: 0.6rem 1rem;
  margin: -1.5rem -1.5rem 1.25rem -1.5rem;
  border-bottom: 1px solid #eee;
  font-weight: 500;
}
.back-bar a { color: #0b57d0; text-decoration: none; }
.back-bar a:hover { text-decoration: underline; }
main { max-width: none; min-width: 0; overflow-x: auto; }
h1 { font-size: 1.8rem; color: #1a1a1a; margin: 0 0 0.5rem; }
h2, h3, h4, h5, h6 { color: #1a1a1a; margin-top: 1.8rem; font-size: 1.15rem; }
a { color: #0b57d0; }
.meta { font-size: 0.8rem; color: #555; }
figure { margin: 1.5rem 0; background: #f6f6f6; padding: 1rem; border: 1px solid #ddd; border-radius: 6px; max-width: 100%; }
figure img { max-width: 100%; height: auto; background: #fff; cursor: zoom-in; }
figcaption { font-size: 0.85rem; color: #555; margin-top: 0.5rem; }
button.zoom { background: none; border: 0; padding: 0; display: block; width: 100%; max-width: 100%; cursor: zoom-in; }
dialog { max-width: 90vw; max-height: 90vh; background: #fff; color: #1a1a1a; border: 1px solid #ccc; border-radius: 8px; padding: 1rem; }
dialog img { max-width: 100%; max-height: 75vh; background: #fff; }
dialog::backdrop { background: rgba(0,0,0,0.5); }
ul { padding-left: 1.2rem; }
table { border-collapse: collapse; width: 100%; max-width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #bbb; padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }
th { background: #f0f0f0; font-weight: 600; }
@media (max-width: 800px) {
  nav.toc {
    position: sticky;
    top: 0;
    left: auto;
    width: 100%;
    height: auto;
    max-height: 45vh;
    border-right: 0;
    border-bottom: 1px solid #ddd;
  }
  .layout:has(nav.toc) main {
    margin-left: 0;
    padding: 1rem;
    max-width: none;
  }
  .back-bar { margin: -1rem -1rem 1rem -1rem; }
}
""".strip()
