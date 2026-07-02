"""TTS 合成引擎：封装 sherpa-onnx OfflineTts 的懒加载与配置缓存。

从 server.py 抽离，合成逻辑与原实现一致。模型按缓存键复用：
(model_dir, vocoder, threads, noise_scale, length_scale, silence_scale,
max_num_sentences) 任一变化才重建 OfflineTts；speed 在 generate 时按请求传入，
改语速不触发模型重载。
"""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

import sherpa_onnx
import soundfile as sf

ROOT = Path(__file__).resolve().parent


def resolve_path(path: str, base: Path = ROOT) -> Path:
    """相对路径按 base 解析，绝对路径原样使用。"""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else base / candidate


class TtsEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tts: sherpa_onnx.OfflineTts | None = None
        self._key: tuple[Any, ...] | None = None

    def synthesize(
        self, text: str, config: dict[str, Any], speed: float | None = None
    ) -> tuple[bytes, float, int]:
        if not text.strip():
            raise ValueError("text is empty")
        tts = self._get_tts(config)
        generated = tts.generate(
            text.strip(), sid=0, speed=float(speed if speed is not None else config["speed"])
        )
        buffer = io.BytesIO()
        sf.write(buffer, generated.samples, generated.sample_rate, format="WAV")
        duration = len(generated.samples) / generated.sample_rate
        return buffer.getvalue(), duration, generated.sample_rate

    def _get_tts(self, config: dict[str, Any]) -> sherpa_onnx.OfflineTts:
        model_dir = resolve_path(config["model_dir"])
        vocoder = resolve_path(config["vocoder"])
        # 缓存键：只有影响模型加载的参数进键。speed 不在内。
        key = (
            str(model_dir),
            str(vocoder),
            int(config["threads"]),
            float(config["noise_scale"]),
            float(config["length_scale"]),
            float(config["silence_scale"]),
            int(config["max_num_sentences"]),
        )
        # 本地桌面服务，全局锁足够；若未来要并发切换多模型再换成 per-model 锁。
        with self._lock:
            if self._tts is not None and self._key == key:
                return self._tts

            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(
                        acoustic_model=str(model_dir / "model-steps-3.onnx"),
                        vocoder=str(vocoder),
                        lexicon=str(model_dir / "lexicon.txt"),
                        tokens=str(model_dir / "tokens.txt"),
                        data_dir=str(model_dir / "espeak-ng-data"),
                        noise_scale=float(config["noise_scale"]),
                        length_scale=float(config["length_scale"]),
                    ),
                    num_threads=int(config["threads"]),
                    debug=False,
                    provider="cpu",
                ),
                rule_fsts=",".join(
                    [
                        str(model_dir / "phone-zh.fst"),
                        str(model_dir / "date-zh.fst"),
                        str(model_dir / "number-zh.fst"),
                    ]
                ),
                max_num_sentences=int(config["max_num_sentences"]),
                silence_scale=float(config["silence_scale"]),
            )

            if not tts_config.validate():
                raise RuntimeError(
                    "invalid TTS config; run scripts/setup first and check model paths"
                )
            self._tts = sherpa_onnx.OfflineTts(tts_config)
            self._key = key
            return self._tts


ENGINE = TtsEngine()
