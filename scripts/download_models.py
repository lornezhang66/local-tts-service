from __future__ import annotations

import urllib.request
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODEL_DIR = MODELS / "matcha-icefall-zh-en"
VOCODER = MODELS / "vocos-16khz-univ.onnx"
VOCODER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos-16khz-univ.onnx"
REQUIRED_MODEL_FILES = [
    "model-steps-3.onnx",
    "lexicon.txt",
    "tokens.txt",
    "phone-zh.fst",
    "date-zh.fst",
    "number-zh.fst",
]


def main() -> None:
    MODELS.mkdir(exist_ok=True)
    if missing_model_files():
        snapshot_download(
            repo_id="csukuangfj/matcha-icefall-zh-en",
            local_dir=MODEL_DIR,
        )
    if not VOCODER.is_file() or VOCODER.stat().st_size == 0:
        print(f"Downloading {VOCODER_URL}")
        urllib.request.urlretrieve(VOCODER_URL, VOCODER)
    missing = missing_model_files()
    if missing:
        lines = "\n".join(f"- {path}" for path in missing)
        raise SystemExit(f"Model download did not produce required files:\n{lines}")
    print("Models are ready.")


def missing_model_files() -> list[Path]:
    missing = [
        MODEL_DIR / name
        for name in REQUIRED_MODEL_FILES
        if not (MODEL_DIR / name).is_file() or (MODEL_DIR / name).stat().st_size == 0
    ]
    if not VOCODER.is_file() or VOCODER.stat().st_size == 0:
        missing.append(VOCODER)
    return missing


if __name__ == "__main__":
    main()
