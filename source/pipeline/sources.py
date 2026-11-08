"""Public source list.

Generated from the manifest (single source of truth).
Written to html/sources.html so it is packaged into the ZIM.
Searchable client-side. Never hand-edited.

Columns: title, filename, sha256, location (basic/extensive/paid), size, category.
"""
from __future__ import annotations
from pathlib import Path
import json
import html as html_lib

def _location(path: str) -> str:
    p = path.replace("\\", "/")
    if "/paid/" in p or p.startswith("paid/"):
        return "paid"
    if "/extensive/" in p or p.startswith("extensive/"):
        return "extensive"
    if "/basic/" in p or p.startswith("basic/"):
        return "basic"
    return "unknown"

def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"

def write_sources_page(html_root: Path, manifest_path: Path) -> Path | None:
    if not manifest_path.exists():
        return None
    data = json.loads(manifest_path.read_text())
    docs = data.get("documents", {})

    rows = []
    for doc_id, rec in sorted(docs.items(), key=lambda kv: (kv[1].get("category", ""), kv[0])):
        path = rec.get("path", "")
        filename = Path(path).name if path else doc_id
        title = rec.get("title") or filename
        category = rec.get("category", "")
        sha = rec.get("sha256", "")
        loc = rec.get("location") or _location(path)
        size = _human_size(int(rec.get("size", 0)))
        # data-search holds the lowercase blob the filter matches against
        blob = " ".join([title, filename, sha, loc, category]).lower()
        rows.append(
            f'<tr data-search="{html_lib.escape(blob)}">'
            f"<td>{html_lib.escape(title)}</td>"
            f"<td>{html_lib.escape(filename)}</td>"
            f'<td><code class="hash" data-hash="{html_lib.escape(sha)}" title="Click to copy">{html_lib.escape(sha)}</code></td>'
            f"<td>{html_lib.escape(loc)}</td>"
            f"<td>{size}</td>"
            f"<td>{html_lib.escape(category)}</td>"
            f"</tr>"
        )

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Source list</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; background: #0c121c; color: #e8eef5; }}
    h1 {{ color: #ffdc50; }}
    a {{ color: #64b4ff; }}
    input {{ width: 100%; max-width: 480px; padding: 0.5rem; margin: 0.5rem 0 1rem; background: #1a2230; color: #e8eef5; border: 1px solid #345; border-radius: 4px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
    th, td {{ border-bottom: 1px solid #243; padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }}
    th {{ color: #8cf; }}
    code {{ font-size: 0.75rem; word-break: break-all; }}
    code.hash {{ cursor: pointer; }}
    code.hash:hover {{ color: #ffdc50; }}
    code.hash.copied {{ color: #8f8; }}
    .count {{ color: #8aa; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <p><a href="index.html">← Back to index</a></p>
  <h1>Source list</h1>
  <p>All ingested sources. SHA-256 identifies the exact PDF bytes. Search matches title, filename, hash, location, or category.</p>
  <input id="q" type="search" placeholder="Search title, filename, hash, location, category…" autofocus>
  <p class="count" id="count"></p>
  <table>
    <thead><tr><th>Title</th><th>Filename</th><th>SHA-256</th><th>Location</th><th>Size</th><th>Category</th></tr></thead>
    <tbody id="rows">
      {"".join(rows) if rows else "<tr><td colspan='6'>No sources ingested yet.</td></tr>"}
    </tbody>
  </table>
  <script>
    const q = document.getElementById("q");
    const rows = Array.from(document.querySelectorAll("#rows tr"));
    const count = document.getElementById("count");
    function filter() {{
      const term = q.value.trim().toLowerCase();
      let shown = 0;
      for (const tr of rows) {{
        const ok = !term || (tr.dataset.search || "").includes(term);
        tr.style.display = ok ? "" : "none";
        if (ok) shown++;
      }}
      count.textContent = shown + " of " + rows.length;
    }}
    q.addEventListener("input", filter);
    filter();
    document.getElementById("rows").addEventListener("click", async (e) => {{
      const el = e.target.closest(".hash");
      if (!el) return;
      const hash = el.dataset.hash || el.textContent;
      try {{
        await navigator.clipboard.writeText(hash);
        el.classList.add("copied");
        const prev = el.textContent;
        el.textContent = "copied";
        setTimeout(() => {{ el.textContent = prev; el.classList.remove("copied"); }}, 800);
      }} catch (err) {{
        el.textContent = "copy failed";
      }}
    }});
  </script>
</body>
</html>
'''
    out = html_root / "sources.html"
    out.write_text(page)
    return out
