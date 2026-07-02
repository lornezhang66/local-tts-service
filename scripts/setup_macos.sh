#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python ./scripts/download_models.py

if [ ! -f "config.json" ]; then
  cp config.example.json config.json
fi

echo "Local TTS Service is ready. Run ./scripts/run_macos.sh"
