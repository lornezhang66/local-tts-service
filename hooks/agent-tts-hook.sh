#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${AGENT_TTS_PYTHON:-$ROOT/../.venv/bin/python}"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"
"$PYTHON" "$ROOT/agent_tts_hook.py" "$@"
