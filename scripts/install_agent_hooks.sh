#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./ttsctl.sh hooks install
