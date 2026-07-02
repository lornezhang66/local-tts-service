from __future__ import annotations

import urllib.request
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
VOCODER = MODELS / "vocos-16khz-univ.onnx"
VOCODER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos-16khz-univ.onnx"


def main() -> None:
    MODELS.mkdir(exist_ok=True)
    snapshot_download(
        repo_id="csukuangfj/matcha-icefall-zh-en",
        local_dir=MODELS / "matcha-icefall-zh-en",
    )
    if not VOCODER.exists():
        print(f"Downloading {VOCODER_URL}")
        urllib.request.urlretrieve(VOCODER_URL, VOCODER)
    print("Models are ready.")


if __name__ == "__main__":
    main()
