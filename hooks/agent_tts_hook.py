from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
EXAMPLE = ROOT / "config.example.json"
STATE = Path(tempfile.gettempdir()) / "agent-tts-hook-state.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["codex", "claude"], required=True)
    parser.add_argument("--event", default="")
    args = parser.parse_args()

    payload = read_stdin_json()
    config = load_config()
    if not config.get("enabled", True):
        return

    text = message_for(args.source, args.event or event_name(payload), config)
    if not text or cooled_down(config):
        return

    wav = synthesize(text, config)
    play_wav(wav)


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        CONFIG.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["api_key"] = os.environ.get("LOCAL_TTS_API_KEY") or config.get("api_key", "")
    config["service_url"] = os.environ.get("LOCAL_TTS_SERVICE_URL") or config.get("service_url", "http://127.0.0.1:8787")
    return config


def event_name(payload: dict[str, Any]) -> str:
    for key in ["hook_event_name", "event", "eventName", "type"]:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "Notification"


def message_for(source: str, event: str, config: dict[str, Any]) -> str:
    messages = config.get("messages", {})
    for key in (f"{source}.{event}", f"{source}.{normalize_event(event)}"):
        if key in messages:
            return str(messages[key])
    return str(messages.get(f"{source}.Notification", "有新的通知。"))


def normalize_event(event: str) -> str:
    lower = event.lower()
    if "permission" in lower:
        return "PermissionRequest"
    if lower.endswith("stop"):
        return "Stop"
    if "session" in lower and "start" in lower:
        return "SessionStart"
    return "Notification"


def cooled_down(config: dict[str, Any]) -> bool:
    now = time.time()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if now - float(state.get("last_spoken_at", 0)) < float(config.get("cooldown_seconds", 6)):
        return True
    STATE.write_text(json.dumps({"last_spoken_at": now}), encoding="utf-8")
    return False


def synthesize(text: str, config: dict[str, Any]) -> Path:
    api_key = config.get("api_key", "")
    if not api_key:
        raise RuntimeError("LOCAL_TTS_API_KEY or hooks/config.json api_key is required")
    request = urllib.request.Request(
        config["service_url"].rstrip("/") + "/api/synthesize",
        data=json.dumps({"text": text, "speed": 1.0}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        wav = response.read()
    path = Path(tempfile.gettempdir()) / f"agent-tts-{int(time.time() * 1000)}.wav"
    path.write_bytes(wav)
    return path


def play_wav(path: Path) -> None:
    if platform.system() == "Windows":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    elif platform.system() == "Darwin":
        subprocess.run(["afplay", str(path)], check=False)
    else:
        subprocess.run(["aplay", str(path)], check=False)
    path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, TimeoutError, urllib.error.URLError):
        sys.exit(0)
