from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODEL_DIR = MODELS / "matcha-icefall-zh-en"
VOCODER = MODELS / "vocos-16khz-univ.onnx"
MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/matcha-icefall-zh-en.tar.bz2"
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
        download_model()
    if not VOCODER.is_file() or VOCODER.stat().st_size == 0:
        print(f"Downloading {VOCODER_URL}")
        urllib.request.urlretrieve(VOCODER_URL, VOCODER)
    missing = missing_model_files()
    if missing:
        lines = "\n".join(f"- {path}" for path in missing)
        raise SystemExit(f"Model download did not produce required files:\n{lines}")
    print("Models are ready.")


def download_model() -> None:
    print(f"Downloading {MODEL_URL}")
    with tempfile.TemporaryDirectory() as temp_dir:
        archive = Path(temp_dir) / "model.tar.bz2"
        urllib.request.urlretrieve(MODEL_URL, archive)
        with tarfile.open(archive, "r:bz2") as model_tar:
            root = Path(temp_dir).resolve()
            if any(
                member.issym() or member.islnk() or root not in (root / member.name).resolve().parents
                for member in model_tar.getmembers()
            ):
                raise SystemExit("Model archive contains an unsafe path.")
            if sys.version_info >= (3, 12):
                model_tar.extractall(temp_dir, filter="fully_trusted")
            else:
                model_tar.extractall(temp_dir)
        extracted = Path(temp_dir) / MODEL_DIR.name
        if not extracted.is_dir():
            raise SystemExit("Model archive has an unexpected directory structure.")
        shutil.rmtree(MODEL_DIR, ignore_errors=True)
        shutil.move(extracted, MODEL_DIR)


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
