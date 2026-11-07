#!/usr/bin/env bash
# ZIM-ham-radio-library — build and optional deploy
# Packages only html/ into a ZIM. source/ is never included.

set -euo pipefail

ZIM_NAME="ham_radio_library"
ZIM_TITLE="Ham Radio Library"
ZIM_DESC="Offline amateur radio reference library (HTML-first) for Project NOMAD / Kiwix"
HTML_DIR="html"
OUTPUT="${ZIM_NAME}.zim"

DEPLOY=false
ZIM_DEST=""
CONTAINER=""

usage() {
  echo "Usage: $0 [--deploy --zim-dest=PATH --container=NAME]"
  echo ""
  echo "  Builds a ZIM from the html/ directory only."
  echo "  With --deploy, copies the ZIM to the given destination and restarts the container."
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy)
      DEPLOY=true
      shift
      ;;
    --zim-dest=*)
      ZIM_DEST="${1#*=}"
      shift
      ;;
    --container=*)
      CONTAINER="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

if [[ ! -d "$HTML_DIR" ]]; then
  echo "Error: $HTML_DIR/ not found"
  exit 1
fi

if [[ ! -f "$HTML_DIR/illustration.png" ]]; then
  echo "Error: $HTML_DIR/illustration.png (48x48) is required by zimwriterfs"
  exit 1
fi

echo "Building $OUTPUT from $HTML_DIR/ ..."
zimwriterfs \
  --welcome=index.html \
  --illustration=illustration.png \
  --language=eng \
  --name="$ZIM_NAME" \
  --title="$ZIM_TITLE" \
  --description="$ZIM_DESC" \
  --longDescription="Exhaustive offline ham radio reference. HTML-first so NOMAD RAG can index it. Figures prefer SVG/vector." \
  "$HTML_DIR" \
  "$OUTPUT"

echo "Built: $OUTPUT"

if [[ "$DEPLOY" == true ]]; then
  if [[ -z "$ZIM_DEST" || -z "$CONTAINER" ]]; then
    echo "Error: --deploy requires --zim-dest=PATH and --container=NAME"
    exit 1
  fi
  echo "Deploying to $ZIM_DEST and restarting $CONTAINER ..."
  sudo cp "$OUTPUT" "$ZIM_DEST/"
  sudo docker restart "$CONTAINER" || true
  echo "Deployed. Remember to add the ZIM in NOMAD Content Manager / Knowledge Base for LLM ingest."
fi
