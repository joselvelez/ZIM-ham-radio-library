# PDF → HTML + SVG conversion

Document the pipeline here. All major design decisions below are locked.

## Requirements

- Output must be clean, self-contained HTML.
- Figures must be accurate. **Strict SVG / vector preference**: native vectors extracted as SVG; raster diagrams recreated as accurate SVG via AI (iterate until fidelity is met). Photos may remain high-quality raster only when vectorization adds no value.
- Finished articles go into `html/articles/` (hybrid topic taxonomy) and are linked from `html/index.html`.
- Only the finished HTML is packaged into the ZIM.
- Mostly automated batch processing with confidence scores and a review queue.
- Early content-based deduplication.
- Structured handling of multi-column layouts, footnotes, tables, and rotated pages.
- Metadata embedded in HTML + central manifest so RAG chunks retain source, page, figure, category, and topic context.

## Locked decisions

### Vectorization
Native vectors → extract as clean SVG.  
Raster diagrams / schematics / band plans / patterns / wiring → AI vectorization / recreation as accurate SVG. Iterate (prompt, model, or cleanup) until the result does not lose, misplace, or degrade information.  
Equipment photos may stay optimized raster when pure vector adds no value.

### Processing model
Default path is unattended batch: extract → (OCR if needed) → AI vectorize figures → assemble semantic HTML → quality checks.  
Emit confidence / quality scores at figure and document level.  
Items below threshold or explicitly flagged high-value go to a review queue for approve / reject / targeted re-run.

### Directory taxonomy (`html/articles/`)
Hybrid topic-based, shallow:

- `manuals/`
- `band-plans/`
- `operating/`
- `antennas/`
- `digital/`
- `reference/`
- `emergency/`

Optional second level only when a category grows large or a clear subgroup appears.  
Filenames stable and descriptive. Index (and future category pages) provide navigation; internal links use relative paths.

### Deduplication
Early, before expensive stages.  
- Exact: SHA-256 of raw PDF bytes.  
- Near-duplicates: text-layer fingerprint (MinHash / SimHash / embedding) + visual/perceptual hash for diagram-heavy or low-text PDFs.  
Prefer higher-quality canonical source (more text, higher resolution, native vectors, later date, etc.).  
Record relationships in a manifest (JSON or SQLite). Only the canonical version proceeds. Review queue can override.

### Layout, tables, footnotes, rotation
Detect via PDF library layout analysis (PyMuPDF or equivalent): columns, blocks, tables, rotation.  
- Reading order: visual sort (top-to-bottom, left column fully before right).  
- Footnotes: extract separately; prefer inline HTML footnotes with anchors.  
- Tables: structured HTML `<table>` when possible; high-quality image + text fallback + review flag otherwise.  
- Rotation: auto-normalize text extraction and figure rendering before vectorization.  
Quality checks for column-order sanity, table presence, footnote resolution. Low-confidence pages to review queue.

### Metadata
Central manifest (same store as dedup) + embedded in HTML:

- Document: title, source/manual name, equipment/entity, version/date if known, canonical ID.  
- Category: primary from directory (`manuals`, `band-plans`, etc.).  
- Topics / tags: secondary multi-value list (e.g. `hf`, `transceiver`, `icom`, `region-2`).  
- Section / page / figure: heading hierarchy, original page numbers where useful, figure number + caption + “SVG recreation” note.  
- Processing (optional): confidence, OCR used, AI vectorization used.

Visible in article header for Kiwix; machine-readable via meta tags or structured block for the extractor. Supports coherent RAG chunks (“from the IC-7300 service manual, section 5.2, original page 37, figure 5-4”).

## Pipeline stages (sketch)

1. **Ingest / staging** — Place the PDF in the correct directory:  
   - `source/pdfs/public/basic/` (≤ 95 MB, tracked)  
   - `source/pdfs/public/extensive/` (> 95 MB, local only)  
   - `source/pdfs/paid/` (any size, local only)  
   Compute hash + fingerprint immediately. Update the manifest. Skip or flag exact/near-duplicates.  
   Extensive and paid files are supplied by the user and ingested the same way; they are simply never committed.
2. **Triage** — Detect text layer vs. scanned, page count, vector presence, complexity, rotation. Assign initial category/topic hints if possible.
3. **Extract** — Text + structure (blocks, reading order), images, native vector paths → SVG. Table detection. Footnote regions.
4. **OCR** (conditional) — For pages with no usable text layer.
5. **Figure handling / vectorization** — Native SVG kept. Raster diagrams → AI vectorization to accurate SVG. Iterate to quality. Photos optional raster.
6. **HTML assembly + cleanup** — Semantic structure (headings, paragraphs, lists, tables, figures with captions). Embed metadata. Consistent styling. Self-contained where practical. Relative links.
7. **Quality gates** — Automated checks (text length, figure presence/accuracy signals, layout sanity, metadata completeness). Low scores or flags → review queue.
8. **Publish** — Write canonical HTML under the appropriate `html/articles/<category>/…`. Update `html/index.html` (or category indexes). Record final paths and metadata in manifest.
9. **Build & verify** — `./install.sh` packages only `html/`. Confirm Kiwix browsing and non-trivial RAG chunk count after NOMAD ingest.

## Tools (starting point, subject to refinement)

- Core PDF: PyMuPDF (fitz) for extraction, layout, vectors, rendering.
- Fallback / cross-check: Poppler (`pdftohtml`, `pdftocairo`).
- OCR: Tesseract or modern model-based (Docling / equivalent) as needed.
- Vectorization: AI image-generation / vector models for raster-to-SVG recreation; classical vectorizers only as assist.
- Manifest: JSON or SQLite.
- HTML: direct generation + light cleanup (no absolute-positioned dumps).

## Notes

Quality over speed on figures. Accuracy is the hard requirement; automation and scores protect throughput.  
Manifest is the single source of truth for dedup, canonical choice, metadata, and processing history.  
Next concrete step: prototype the ingest → extract → one AI vectorization → HTML path on a small set of representative PDFs (clean manual + diagram-heavy page + scanned page) and validate both visual fidelity and RAG chunk quality.

## Prototype status (2026-11-08)

Minimal working slice under `source/pipeline/`:

- `ingest.py` — SHA-256 + simple fingerprint, manifest.json update, exact/near-dup check.
- `extract.py` — PyMuPDF text blocks (reading-order sorted), native vector detection, SVG export via `get_svg_image()`, page render for AI path.
- `assemble.py` — semantic HTML with metadata (`<meta name="category">` etc.), figure embedding, written to `html/articles/<category>/`.
- `run.py` — end-to-end entrypoint. Also stubs the AI raster→SVG path.

Sample: `source/pdfs/public/basic/sample-band-plan.pdf` (tiny band-plan with native vector diagram).

Setup (once per clone):
```bash
./source/setup.sh
source .venv/bin/activate
```

Run (single file or directory):
```bash
python3 source/pipeline/run.py source/pdfs/public/basic/ --category band-plans
```

Outputs:
- `source/manifest.json`
- `html/articles/band-plans/sample.html` + co-located SVG
- index.html updated with link

Next increments: better reading-order / column handling, real AI vectorization call (or local model), confidence scoring, review queue, multi-page, dedup refinement.

## Figure extraction rule (locked)

Single source of truth in `source/pipeline/figures.py`:

- A figure region is the tight union of native vector drawing items.
- Text whose bounding box intersects that region (plus a small margin) is a figure label.
- Everything else is body text.
- The diagram SVG contains only the vector items inside the region plus those labels.
- The same classification is used for both HTML body text and SVG content. No second filter, no content-specific word lists.

## Running the pipeline

```bash
python3 source/pipeline/run.py <path> [--category NAME] [--pages N] [--html-root DIR]
```

`<path>` is a single PDF or a drop-zone directory. A directory processes every PDF in it (flat; no category subfolders).

```bash
# every PDF already in basic/, using each file's stored category
python3 source/pipeline/run.py source/pdfs/public/basic/

# first time you see a file: set its category once (triage)
python3 source/pipeline/run.py source/pdfs/public/basic/some-manual.pdf --category manuals

# prototype limit: only the first 5 pages
python3 source/pipeline/run.py source/pdfs/public/basic/ --pages 5
```

### Flags

- **positional `<path>`** — a PDF file, or a drop zone (`source/pdfs/public/basic/`, `.../extensive/`, or `source/pdfs/paid/`). Drop PDFs flat in one of those three. Do not create category subdirectories.
- **`--category NAME`** — triage only. Sets the topic for files that do not have one yet, and stores it in the manifest. Already-triaged files ignore it unless you pass it again to change the stored value. Valid names are the topic taxonomy: `manuals`, `band-plans`, `operating`, `antennas`, `digital`, `reference`, `emergency`. There is no default. A new file with no category stops and asks you to re-run with this flag.
- **`--pages N`** — max pages to extract per PDF. Default is 5 (prototype). Omit only when you want the full document.
- **`--html-root DIR`** — where finished HTML is written. Default is `html/`.

Category is not a folder and not a flag you pass every time. It lives in the manifest. `--category` is how you set it the first time.


## Public source list

`html/sources.html` is a searchable list of every ingested source, generated from the manifest and packaged into the ZIM. It is the public view of what the library contains.

Columns:

- **Title** — document title (from the record, or filename stem)
- **Filename** — original PDF name
- **SHA-256** — exact file identity; click to copy
- **Location** — drop zone: `basic`, `extensive`, or `paid`
- **Size** — file size
- **Category** — topic taxonomy (`manuals`, `band-plans`, etc.)

A search box filters the table by any of those fields. The page is regenerated at the end of every pipeline run; do not edit it by hand.

![Source list mockup](docs/sources-list-mockup.svg)

