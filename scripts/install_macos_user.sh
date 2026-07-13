#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="$HOME/Library/Application Support/LocalTTS"
APP_DIR="$INSTALL_ROOT/local-tts-service"
INSTALL_REF="${LOCAL_TTS_INSTALL_REF:-main}"

if [ ! -f "$APP_DIR/ttsctl.sh" ]; then
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  curl -fL "https://github.com/lornezhang66/local-tts-service/archive/$INSTALL_REF.tar.gz" -o "$TMP_DIR/local-tts.tar.gz"
  tar -xzf "$TMP_DIR/local-tts.tar.gz" -C "$TMP_DIR"
  mkdir -p "$INSTALL_ROOT"
  mv "$(find "$TMP_DIR" -maxdepth 1 -type d -name 'local-tts-service-*' -print -quit)" "$APP_DIR"
fi

chmod +x "$APP_DIR/ttsctl.sh"
"$APP_DIR/ttsctl.sh" install
