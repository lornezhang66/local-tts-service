#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="$HOME/Library/Application Support/LocalTTS"
APP_DIR="$INSTALL_ROOT/local-tts-service"

if [ ! -f "$APP_DIR/ttsctl.sh" ]; then
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  curl -fL "https://github.com/lornezhang66/local-tts-service/archive/refs/heads/main.tar.gz" -o "$TMP_DIR/local-tts.tar.gz"
  tar -xzf "$TMP_DIR/local-tts.tar.gz" -C "$TMP_DIR"
  mkdir -p "$INSTALL_ROOT"
  mv "$TMP_DIR/local-tts-service-main" "$APP_DIR"
fi

chmod +x "$APP_DIR/ttsctl.sh"
"$APP_DIR/ttsctl.sh" install
