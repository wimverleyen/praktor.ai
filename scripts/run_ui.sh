#!/usr/bin/env bash
# Launch the praktor.ai Streamlit UI
# Usage: ./scripts/run_ui.sh [--port 8501]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."

cd "$ROOT"
PYTHONPATH="$ROOT/praktor" streamlit run praktor/ui/app.py "$@"
