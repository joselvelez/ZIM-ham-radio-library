#!/usr/bin/env python3
"""Pipeline: ingest → extract → (vector stub) → quality → HTML → stable index.

Usage:
  python3 source/pipeline/run.py path/to/file.pdf --category band-plans
  python3 source/pipeline/run.py source/pdfs/public/basic/ --category band-plans

Flags:
  --category   Triage assignment for files that do not yet have a category.
  --pages N    Debug-only limit. Requires --debug. Default is the full document.
  --debug      Allow --pages. Without this flag, --pages is rejected.
  --html-root  Output root (default: html).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from source.pipeline.ingest import ingest_pdf, load_manifest, save_manifest
from source.pipeline.extract import extract_pdf, extract_diagram_pngs, is_poster, is_scan, extract_scan, render_page_png
from source.pipeline.figures import figure_regions
from source.pipeline.assemble import write_article, retire_other_copies
from source.pipeline.quality import score_document, enqueue_if_low
from source.pipeline.index import rebuild_index
from source.pipeline.sources import write_sources_page
from source.pipeline.title import document_title, variant_qualifier, disambiguate
from source.pipeline.categories import category_from_filename
import pymupdf as fitz


def ai_vectorize_stub(rendered_path: Path) -> str | None:
    """Placeholder for AI raster → accurate SVG recreation."""
    print(f"[AI vectorization stub] Would recreate diagram from {rendered_path}")
    return None


def process_one(pdf: Path, category: str, html_root: Path, max_pages: int | None, force: bool = False, title_override: str | None = None) -> None:
    print(f"\n=== Processing {pdf.name} ===")
    record = ingest_pdf(pdf, category=category)
    if not record.get("category"):
        raise SystemExit(f"No category for {pdf.name}. Re-run with --category to triage it.")

    article = html_root / "articles" / record["category"] / f"{record['id']}.html"
    category_changed = bool(record.get("_previous_category"))
    if article.exists() and not force and not category_changed and not title_override:
        print(f"Already done: {article}")
        return

    manifest = load_manifest()
    docs = manifest.setdefault("documents", {})
    stored = docs.get(record["id"], record)

    if title_override:
        title = title_override.strip()
        if not title:
            raise SystemExit("--title cannot be empty")
        record["title"] = title
        record["title_source"] = "manual"
    elif stored.get("title_source") == "manual" and stored.get("title"):
        title = stored["title"]
        record["title"] = title
        record["title_source"] = "manual"
    else:
        title = document_title(pdf)
        qualifier = variant_qualifier(pdf)
        base = title
        others = [
            (did, rec) for did, rec in docs.items()
            if did != record["id"] and (rec.get("title") or "").split(" (")[0] == base
        ]
        if others:
            fallback = pdf.stem
            title = disambiguate(base, qualifier, fallback)
            for did, rec in others:
                other_path = Path(rec.get("path", ""))
                other_q = variant_qualifier(other_path) if other_path.name else ""
                other_fallback = other_path.stem
                if other_q or other_fallback:
                    rec["title"] = disambiguate(base, other_q, other_fallback)
        record["title"] = title
        record["title_source"] = "resolved"

    if record["id"] in docs:
        docs[record["id"]]["title"] = record["title"]
        docs[record["id"]]["title_source"] = record.get("title_source", "resolved")
        save_manifest(manifest)
    print(f"Title: {title}")

    notes = Path("source/notes")
    notes.mkdir(parents=True, exist_ok=True)

    if is_scan(pdf):
        extracted = extract_scan(pdf, notes, record["id"], max_pages=max_pages)
        print(f"Pages: {extracted['page_count']}, extracted: {extracted['pages_extracted']}")
        retire_other_copies(record, html_root)
        article = write_article(record, extracted, html_root, figures=extracted["figures"])
        print(f"Article: {article}")
        return

    if max_pages is None:
        print("Extracting (full document)...")
    else:
        print(f"Extracting (debug limit: {max_pages} pages)...")
    extracted = extract_pdf(pdf, max_pages=max_pages)
    chunks = extracted.get("chunks") or []
    print(f"Pages: {extracted['page_count']}, extracted: {len(chunks)}")

    notes = Path("source/notes")
    notes.mkdir(parents=True, exist_ok=True)

    if is_poster(extracted["page_count"]):
        print("Poster (one page): rendering the page, not reflowing.")
        doc = fitz.open(pdf)
        page_image = render_page_png(doc[0], notes, record["id"])
        doc.close()
        print(f"  page: {page_image['path']}")
        retire_other_copies(record, html_root)
        article = write_article(record, extracted, html_root, page_image=page_image)
        print(f"Article: {article}")
        return

    figures: list[dict] = []
    doc = fitz.open(pdf)
    # Figures are scanned across the whole document.
    print(f"Scanning {doc.page_count} pages for diagrams...")
    for i in range(doc.page_count):
        regions = figure_regions(doc[i])
        if not regions:
            continue
        results = extract_diagram_pngs(doc[i], notes, f"{record['id']}-page{i}")
        if results:
            for r in results:
                figures.append(r)
                print(f"  diagram on page {i + 1}: {r['path']}")
    doc.close()
    print(f"Diagrams: {len(figures)}")

    svg_ok = bool(figures)
    quality = score_document(extracted, svg_ok)
    print(f"Score: {quality['score']} (text={quality['text_score']}, figure={quality['figure_score']}, cpp={quality['chars_per_page']})")
    review = enqueue_if_low(record, quality)
    if review:
        print(f"Queued for review: {review}")

    retire_other_copies(record, html_root)
    article = write_article(record, extracted, html_root, figures)
    print(f"Article: {article}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path, help="PDF file or directory of PDFs")
    ap.add_argument("--category", default=None, help="Triage: set category for files that do not have one yet")
    ap.add_argument("--html-root", type=Path, default=Path("html"))
    ap.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Debug-only page limit. Requires --debug. Default is the full document.",
    )
    ap.add_argument(
        "--debug",
        action="store_true",
        help="Allow --pages. Without this flag, --pages is rejected (Fail Fast).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Reprocess a file that already has an article. On a directory, reprocess every file.",
    )
    ap.add_argument(
        "--title",
        default=None,
        help="Set the document title. Stored on the manifest and used for the article, index, and sources page. Not overwritten by later runs.",
    )
    args = ap.parse_args()

    if args.pages is not None and not args.debug:
        raise SystemExit(
            "--pages is a debug-only limit and requires --debug. "
            "Omit --pages to extract the full document."
        )
    if args.pages is not None and args.pages < 1:
        raise SystemExit("--pages must be a positive integer")

    target = args.path.resolve()
    if not target.exists():
        print(f"Not found: {target}")
        sys.exit(1)

    pdfs = sorted(target.rglob("*.pdf")) if target.is_dir() else [target]
    if not pdfs:
        print(f"No PDFs in {target}")
        sys.exit(1)

    for pdf in pdfs:
        # --category is an explicit override. Otherwise the filename prefix is the triage.
        # The manifest still wins for a file that already has a category.
        category = args.category or category_from_filename(pdf)
        process_one(pdf, category, args.html_root, args.pages, force=args.force, title_override=args.title)

    rebuild_index(args.html_root)
    src = write_sources_page(args.html_root, Path("source/manifest.json"))
    print(f"\nIndex rebuilt. Sources page: {src}")
    print("Done.")


if __name__ == "__main__":
    main()
