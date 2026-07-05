#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"

if [ ! -x "$PYTHON" ] && [ "${1:-}" = "install" ]; then
  for candidate in "${PYTHON_BOOTSTRAP:-}" python3.12 python3.11 python3.10 python3; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" -m venv "$ROOT/.venv"
      break
    fi
  done
fi

if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
"$PYTHON" "$ROOT/ttsctl.py" "$@"
