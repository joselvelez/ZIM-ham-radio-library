#!/usr/bin/env bash
# Run Graphify on the pipeline and print the graph location.
# Requires the venv from ./source/setup.sh (graphifyy is in requirements.txt).

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Extracting code knowledge graph for source/pipeline ..."
graphify extract source/pipeline

echo ""
echo "Graph written under source/pipeline/graphify-out/"
echo "Query examples:"
echo "  graphify query 'reading order'"
echo "  graphify query 'figure'"
echo "  graphify path extract_page column_order"
