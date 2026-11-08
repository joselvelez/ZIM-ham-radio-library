# NOMAD Add-on: Ham Radio Library

This add-on delivers an offline ham radio reference library as a ZIM for Project NOMAD’s Kiwix Information Library.

## What the add-on install delivers

Only the finished ZIM (built from clean HTML articles).  
It does **not** include original PDFs or the conversion pipeline.

## Install / deploy

On the build machine:

```bash
sudo apt install zim-tools python3
chmod +x install.sh
./install.sh
```

On a NOMAD host:

```bash
./install.sh --deploy \
  --zim-dest=/opt/project-nomad/storage/zim \
  --container=nomad_kiwix_server
```

## Making the content usable by the NOMAD LLM

Deploying the ZIM is not enough. You must ingest it:

1. In NOMAD, open Content Manager / Knowledge Base.
2. Explicitly add the new ZIM (Manual ingest is the default on new installs).
3. NOMAD’s extractor indexes `text/html` and `application/xhtml+xml` entries and creates RAG chunks.
4. Confirm the chunk count is non-trivial. Near-zero means the content is still mostly non-HTML and the LLM cannot use it.

Once chunks exist, the AI Assistant can answer questions from the library.  
Kiwix can browse the same HTML as soon as the ZIM is served.

## Requirements for usable content

- Articles must be clean, self-contained HTML.
- Pictures and diagrams must be accurate (prefer SVG/vector over scanned raster).
