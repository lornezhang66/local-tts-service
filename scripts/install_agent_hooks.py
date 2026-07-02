from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
HOOK_CONFIG = HOOKS / "config.json"
HOOK_EXAMPLE = HOOKS / "config.example.json"
CODEX_HOME = Path.home() / ".codex"
CLAUDE_HOME = Path.home() / ".claude"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", action="store_true", help="Install Codex hooks")
    parser.add_argument("--claude", action="store_true", help="Install Claude Code hooks")
    parser.add_argument("--all", action="store_true", help="Install both Codex and Claude Code hooks")
    args = parser.parse_args()

    install_codex = args.all or args.codex or not (args.codex or args.claude)
    install_claude = args.all or args.claude or not (args.codex or args.claude)

    ensure_hook_config()
    if install_codex:
        install_codex_hooks()
    if install_claude:
        install_claude_hooks()

    print("Agent TTS hooks installed. Review/trust hooks in Codex with /hooks if prompted.")


def ensure_hook_config() -> None:
    config = json.loads(HOOK_EXAMPLE.read_text(encoding="utf-8"))
    if HOOK_CONFIG.exists():
        config.update(json.loads(HOOK_CONFIG.read_text(encoding="utf-8")))
    if not config.get("api_key"):
        key = read_first_run_api_key()
        if key:
            config["api_key"] = key
    HOOK_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def read_first_run_api_key() -> str:
    path = ROOT / "data" / "first-run-credentials.txt"
    if not path.exists():
        return ""
    match = re.search(r"默认 API Key:\s*(\S+)", path.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def install_codex_hooks() -> None:
    target = CODEX_HOME / "hooks.json"
    source = json.loads((HOOKS / "codex-hooks.json").read_text(encoding="utf-8"))
    current = read_json(target, {"hooks": {}})
    current["hooks"] = merge_hooks(current.get("hooks", {}), source["hooks"])
    backup(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Codex hooks installed: {target}")


def install_claude_hooks() -> None:
    target = CLAUDE_HOME / "settings.json"
    source = json.loads((HOOKS / "claude-hooks.json").read_text(encoding="utf-8"))
    current = read_json(target, {})
    current["hooks"] = merge_hooks(current.get("hooks", {}), source["hooks"])
    backup(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Claude Code hooks installed: {target}")


def merge_hooks(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = dict(current)
    for event, groups in incoming.items():
        result.setdefault(event, [])
        existing_commands = {
            hook.get("command")
            for group in result[event]
            for hook in group.get("hooks", [])
            if isinstance(hook, dict)
        }
        for group in groups:
            commands = [hook.get("command") for hook in group.get("hooks", []) if isinstance(hook, dict)]
            if any(command not in existing_commands for command in commands):
                result[event].append(group)
    return result


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-{stamp}"))


if __name__ == "__main__":
    main()
