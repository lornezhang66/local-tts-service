from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import platform
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / "data" / "tts-service.pid"
MODEL_DIR = ROOT / "models" / "matcha-icefall-zh-en"
VOCODER_FILE = ROOT / "models" / "vocos-16khz-univ.onnx"
REQUIRED_MODEL_FILES = [
    "model-steps-3.onnx",
    "lexicon.txt",
    "tokens.txt",
    "phone-zh.fst",
    "date-zh.fst",
    "number-zh.fst",
]
DEFAULT_CONFIG = {
    "model_dir": "models/matcha-icefall-zh-en",
    "vocoder": "models/vocos-16khz-univ.onnx",
    "threads": 6,
    "speed": 1.0,
    "noise_scale": 0.667,
    "length_scale": 1.0,
    "silence_scale": 0.2,
    "max_num_sentences": 1,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="ttsctl")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("install")

    start = sub.add_parser("start")
    start.add_argument("--background", action="store_true")
    start.add_argument("--open", action="store_true")

    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("test")

    say = sub.add_parser("say")
    say.add_argument("text")
    say.add_argument("--output", default=str(ROOT / "data" / "ttsctl-say.wav"))
    say.add_argument("--speed", type=float)
    say.add_argument("--play", action="store_true")

    hooks = sub.add_parser("hooks")
    hooks_sub = hooks.add_subparsers(dest="hooks_cmd", required=True)
    hooks_sub.add_parser("install")
    hooks_sub.add_parser("uninstall")
    hooks_sub.add_parser("status")

    args = parser.parse_args()
    if args.cmd == "install":
        install()
    elif args.cmd == "start":
        start_service(args.background, args.open)
    elif args.cmd == "stop":
        stop_service()
    elif args.cmd == "status":
        status()
    elif args.cmd == "test":
        smoke_test()
    elif args.cmd == "say":
        say_offline(args.text, Path(args.output), args.speed, args.play)
    elif args.cmd == "hooks":
        if args.hooks_cmd == "install":
            hooks_install()
        elif args.hooks_cmd == "uninstall":
            hooks_uninstall()
        elif args.hooks_cmd == "status":
            hooks_status()


def install() -> None:
    run([python(), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([python(), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    run([python(), str(ROOT / "scripts" / "download_models.py")])
    print("Install complete. Run: ttsctl start --background")


def start_service(background: bool, open_browser: bool) -> None:
    args = [python(), str(ROOT / "server.py")]
    if open_browser:
        args.append("--open")
    if not background:
        run(args)
        return
    ROOT.joinpath("data").mkdir(exist_ok=True)
    proc = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(2)
    print(f"Started Local TTS Service, pid={proc.pid}")


def stop_service() -> None:
    if not PID_FILE.exists():
        print("No pid file. If the service was started manually, stop that process manually.")
        return
    pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
    else:
        subprocess.run(["kill", str(pid)], check=False)
    PID_FILE.unlink(missing_ok=True)
    print("Stopped Local TTS Service.")


def status() -> None:
    try:
        data = request_json("http://127.0.0.1:8787/api/health")
        print(f"Service: {'ok' if data.get('ok') else 'unknown'}")
    except Exception as exc:
        print(f"Service: offline ({exc})")
    hooks_status()


def smoke_test() -> None:
    key = hook_api_key()
    if not key:
        raise SystemExit("Missing hooks/config.json api_key. Run: ttsctl hooks install")
    req = urllib.request.Request(
        "http://127.0.0.1:8787/api/synthesize",
        data=json.dumps({"text": "本地 TTS 服务测试成功。", "speed": 1.0}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        wav = res.read()
    out = ROOT / "data" / "ttsctl-test.wav"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(wav)
    print(f"Test OK: {out}")


def say_offline(text: str, output: Path, speed: float | None, play: bool) -> None:
    ensure_models()

    from tts_engine import ENGINE

    config = load_tts_config()
    output.parent.mkdir(parents=True, exist_ok=True)
    wav, duration, sample_rate = ENGINE.synthesize(text, config, speed=speed)
    output.write_bytes(wav)
    print(f"Offline TTS OK: {output} ({duration:.2f}s, {sample_rate}Hz)")
    if play:
        play_wav(output)


def ensure_models() -> None:
    missing = missing_model_files()
    if not missing:
        return
    print("Models are missing or incomplete:")
    for path in missing:
        print(f"- {path}")
    print("Downloading models...")
    run([python(), str(ROOT / "scripts" / "download_models.py")])
    missing_after_download = missing_model_files()
    if missing_after_download:
        lines = "\n".join(f"- {path}" for path in missing_after_download)
        raise SystemExit(f"Model download did not produce required files:\n{lines}")


def missing_model_files() -> list[Path]:
    required = [MODEL_DIR / name for name in REQUIRED_MODEL_FILES]
    required.append(VOCODER_FILE)
    return [path for path in required if not path.is_file() or path.stat().st_size == 0]


def hooks_install() -> None:
    run([python(), str(ROOT / "scripts" / "install_agent_hooks.py"), "--all"])


def hooks_uninstall() -> None:
    remove_hook_commands(Path.home() / ".codex" / "hooks.json")
    remove_hook_commands(Path.home() / ".claude" / "settings.json")
    print("Agent hooks removed.")


def hooks_status() -> None:
    for name, path in {
        "Codex": Path.home() / ".codex" / "hooks.json",
        "Claude": Path.home() / ".claude" / "settings.json",
    }.items():
        if not path.exists():
            print(f"{name} hooks: missing")
            continue
        text = path.read_text(encoding="utf-8")
        print(f"{name} hooks: {'installed' if 'agent-tts-hook' in text else 'not installed'}")


def remove_hook_commands(path: Path) -> None:
    if not path.exists():
        return
    backup(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    for event in list(hooks.keys()):
        groups = []
        for group in hooks[event]:
            next_hooks = [
                item
                for item in group.get("hooks", [])
                if "agent-tts-hook" not in str(item.get("command", ""))
            ]
            if next_hooks:
                group["hooks"] = next_hooks
                groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hook_api_key() -> str:
    path = ROOT / "hooks" / "config.json"
    if not path.exists():
        return ""
    return json.loads(path.read_text(encoding="utf-8")).get("api_key", "")


def load_tts_config() -> dict:
    path = ROOT / "data" / "config.json"
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        config.update(json.loads(path.read_text(encoding="utf-8")))
    return config


def play_wav(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    elif system == "Darwin":
        subprocess.run(["afplay", str(path)], check=False)
    else:
        subprocess.run(["aplay", str(path)], check=False)


def request_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as res:
        return json.loads(res.read().decode("utf-8"))


def backup(path: Path) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-{stamp}"))


def python() -> str:
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate if candidate.exists() else sys.executable)


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, urllib.error.URLError) as exc:
        raise SystemExit(str(exc))
