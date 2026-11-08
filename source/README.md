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
