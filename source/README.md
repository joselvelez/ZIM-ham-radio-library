# Source materials

Original PDFs and conversion work live here.  
**Not packaged into the ZIM.** The NOMAD add-on install never includes this directory.

## PDF locations

- `pdfs/public/basic/`  
  Public PDFs ≤ 95 MB. Tracked in ordinary git (no LFS). These are the “batteries included” sources that come with a clone.

- `pdfs/public/extensive/`  
  Public PDFs > 95 MB. Not tracked. The user must place the files here locally and run them through the conversion pipeline.

- `pdfs/paid/`  
  Any paid, personal, or DRM-restricted PDF (any size). Not tracked. The user must place the files here locally and run them through the conversion pipeline.  
  Handled identically to extensive public files: provide the PDF → ingest → convert. Nothing is ever pushed.

- `notes/` — intermediate extraction / conversion notes
- `CONVERSION.md` — pipeline definition

GitHub rejects files > 100 MB. The 95 MB cutoff stays just under that hard limit so basic content can be committed with ordinary git.  
Extensive and paid sources are local-only inputs; the rest of the pipeline does not distinguish them.

## Prototype pipeline

See `pipeline/` and the "Prototype status" section in `CONVERSION.md`.
A minimal end-to-end slice (ingest → extract → SVG → HTML) is available for validation.

## Setup (required after clone)

The pipeline needs Python 3.10–3.13 (onnxruntime has no wheel for 3.14+) and a virtualenv. From the repo root:

```bash
./source/setup.sh
source .venv/bin/activate
```

Then process PDFs (full document by default):

```bash
python3 source/pipeline/run.py source/pdfs/public/basic/ --category band-plans
```

Debug-only page limit (requires `--debug`):

```bash
python3 source/pipeline/run.py path/to/file.pdf --category manuals --debug --pages 5
```

Graphify (local code knowledge graph) is installed by setup. To analyze the pipeline:

```bash
./source/graphify.sh
# or
graphify extract source/pipeline
```

`.venv/` is gitignored. Re-run `./source/setup.sh` after pulling if `source/requirements.txt` changes.

See CONVERSION.md for the public source list (`html/sources.html`) and the locked implementation decisions (reading order, figure placement, SVG cleanup, captions, `--pages` flag).
