#!/bin/bash
# Run AircraftX from the git tree without pip install.
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

if ! command -v hackrf_transfer >/dev/null 2>&1; then
  echo "hackrf_transfer not found. Install with: brew install hackrf" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Run 'make dev-install' first." >&2
  exit 1
fi

source .venv/bin/activate
exec python3 -m aircraftx "$@"
