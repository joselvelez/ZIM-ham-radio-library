"""Stable index update.

Rebuilds the Articles section of html/index.html from the files that actually
exist under html/articles/. No string-replace hacks, no duplicates.

Articles are sorted alphabetically by title (case-insensitive).
The list is rendered in two columns via CSS (class articles-list) to reduce scrolling.
"""
from __future__ import annotations
from pathlib import Path
import re

ARTICLES_RE = re.compile(
    r"(<h2>Articles</h2>\s*<ul(?:\s+class=\"articles-list\")?>)(.*?)(</ul>)",
    re.DOTALL,
)

TWO_COL_CSS = """
    ul.articles-list {
      column-count: 2;
      column-gap: 2.5rem;
      list-style-position: outside;
      padding-left: 1.2rem;
      margin: 0.5rem 0 1.5rem;
    }
    ul.articles-list li {
      break-inside: avoid;
      margin-bottom: 0.35rem;
    }
    @media (max-width: 720px) {
      ul.articles-list { column-count: 1; }
    }
"""

def _ensure_two_column_css(content: str) -> str:
    """Make sure the index <style> contains the two-column rules and a wider max-width."""
    if "ul.articles-list" in content and "column-count: 2" in content:
        return content
    # Insert before the closing </style>
    if "</style>" in content:
        content = content.replace("</style>", TWO_COL_CSS + "  </style>", 1)
    # Widen body max-width if still the old 800px
    content = content.replace("max-width: 800px;", "max-width: 1100px;")
    return content

def rebuild_index(html_root: Path) -> None:
    """Scan html/articles/**/*.html and rewrite the index list."""
    index = html_root / "index.html"
    if not index.exists():
        return
    articles_dir = html_root / "articles"
    entries = []
    if articles_dir.exists():
        for html in articles_dir.rglob("*.html"):
            rel = html.relative_to(html_root).as_posix()
            # title from <h1> or filename
            text = html.read_text(errors="ignore")
            m = re.search(r"<h1>(.*?)</h1>", text)
            title = m.group(1).strip() if m else html.stem.replace("-", " ").title()
            entries.append((title, rel))
        # Alphabetical by title (case-insensitive)
        entries.sort(key=lambda t: t[0].lower())
        entries = [f'    <li><a href="{rel}">{title}</a></li>' for title, rel in entries]

    content = index.read_text()
    content = _ensure_two_column_css(content)
    new_ul = '<h2>Articles</h2>\n  <ul class="articles-list">\n' + "\n".join(entries) + "\n  </ul>"
    if ARTICLES_RE.search(content):
        content = ARTICLES_RE.sub(new_ul, content, count=1)
    else:
        # fallback: append before </body>
        content = content.replace("</body>", new_ul + "\n</body>", 1)
    # ensure a link to the public source list
    if 'href="sources.html"' not in content:
        content = content.replace(
            "</ul>",
            '</ul>\n  <p><a href="sources.html">Source list (with hashes)</a></p>',
            1,
        )
    index.write_text(content)
