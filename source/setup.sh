#!/usr/bin/env bash
# One-time setup for the conversion pipeline.
# Creates a local virtualenv and installs the Python dependencies.
# Safe to re-run.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r source/requirements.txt

echo ""
echo "Setup complete."
echo "Activate the environment with:"
echo "  source .venv/bin/activate"
echo ""
echo "Then run the pipeline, for example:"
echo "  python3 source/pipeline/run.py source/pdfs/public/basic/ --category band-plans"
