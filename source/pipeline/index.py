"""Stable index update.

Rebuilds the Articles section of html/index.html from the files that actually
exist under html/articles/. No string-replace hacks, no duplicates.
"""
from __future__ import annotations
from pathlib import Path
import re

ARTICLES_RE = re.compile(r"(<h2>Articles</h2>\s*<ul>)(.*?)(</ul>)", re.DOTALL)

def rebuild_index(html_root: Path) -> None:
    """Scan html/articles/**/*.html and rewrite the index list."""
    index = html_root / "index.html"
    if not index.exists():
        return
    articles_dir = html_root / "articles"
    entries = []
    if articles_dir.exists():
        for html in sorted(articles_dir.rglob("*.html")):
            rel = html.relative_to(html_root).as_posix()
            # title from <h1> or filename
            text = html.read_text(errors="ignore")
            m = re.search(r"<h1>(.*?)</h1>", text)
            title = m.group(1).strip() if m else html.stem.replace("-", " ").title()
            entries.append(f'    <li><a href="{rel}">{title}</a></li>')

    content = index.read_text()
    new_ul = "<h2>Articles</h2>\n  <ul>\n" + "\n".join(entries) + "\n  </ul>"
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
