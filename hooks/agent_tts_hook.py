from __future__ import annotations

import argparse
import json
import os
import platform
import re
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

    text = clean_markdown_for_speech(
        message_for(args.source, args.event or event_name(payload), config, payload)
    )
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
    config["mode"] = os.environ.get("LOCAL_TTS_MODE") or config.get("mode", "cli")
    config["service_url"] = os.environ.get("LOCAL_TTS_SERVICE_URL") or config.get("service_url", "http://127.0.0.1:8787")
    return config


def event_name(payload: dict[str, Any]) -> str:
    for key in ["hook_event_name", "event", "eventName", "type"]:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "Notification"


def message_for(
    source: str, event: str, config: dict[str, Any], payload: dict[str, Any] | None = None
) -> str:
    if source == "codex" and normalize_event(event) == "Stop":
        text = codex_stop_text(payload or {})
        if text:
            return text

    messages = config.get("messages", {})
    for key in (f"{source}.{event}", f"{source}.{normalize_event(event)}"):
        if key in messages:
            return str(messages[key])
    return str(messages.get(f"{source}.Notification", "有新的通知。"))


def codex_stop_text(payload: dict[str, Any]) -> str:
    for key in (
        "last_assistant_message",
        "assistant_message",
        "assistant_response",
        "final_response",
        "output_text",
        "response",
    ):
        text = string_content(payload.get(key))
        if text:
            return text

    text = last_assistant_message(payload)
    if text:
        return text

    transcript = payload.get("transcript_path") or payload.get("conversation_path")
    if isinstance(transcript, str):
        return last_assistant_from_jsonl(Path(transcript))
    return ""


def last_assistant_message(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("role") == "assistant":
            text = string_content(value.get("content") or value.get("message") or value.get("text"))
            if text:
                return text
        for key in ("payload", "data", "messages", "items", "events", "conversation"):
            text = last_assistant_message(value.get(key))
            if text:
                return text
    if isinstance(value, list):
        for item in reversed(value):
            text = last_assistant_message(item)
            if text:
                return text
    return ""


def last_assistant_from_jsonl(path: Path) -> str:
    if not path.is_file():
        return ""
    text = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = last_assistant_message(data) or text
    return text


def string_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [string_content(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            text = string_content(value.get(key))
            if text:
                return text
    return ""


def clean_markdown_for_speech(text: str) -> str:
    text = keep_plain_text_fences(text)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*]\([^)]*\)", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"[-:| ]{3,}", line) or re.fullmatch(r"[-*_]{3,}", line):
            continue
        if "|" in line and re.search(r"\s\|\s|^\||\|$", line):
            line = line.replace("|", " ")
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = re.sub(r"\[[ xX]]\s*", "", line)
        line = re.sub(r"[*_~]{1,3}", "", line)
        line = re.sub(r"[\w./~ -]+:\d+(?::\d+)?", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    text = "。".join(lines)
    text = re.sub(r"[。．.]{2,}", "。", text)
    return text.strip("。 ")


def keep_plain_text_fences(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        language = (match.group(1) or "").strip().lower().split()
        if language and language[0] in {"text", "txt", "plain", "plaintext"}:
            return "\n" + match.group(2).strip("\n") + "\n"
        return "\n"

    return re.sub(r"(?ms)^```[ \t]*([^\n`]*)\n(.*?)^```[ \t]*$", replace, text)


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
    if config.get("mode", "cli") == "cli":
        return synthesize_cli(text, config)

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


def synthesize_cli(text: str, config: dict[str, Any]) -> Path:
    sys.path.insert(0, str(ROOT.parent))
    from tts_engine import ENGINE
    from ttsctl import load_tts_config

    wav, _, _ = ENGINE.synthesize(text, load_tts_config(), speed=config.get("speed"))
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
