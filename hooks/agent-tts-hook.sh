#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
"${AGENT_TTS_PYTHON:-python3}" "$ROOT/agent_tts_hook.py" "$@"
