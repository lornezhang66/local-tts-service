from __future__ import annotations

import json
from unittest.mock import patch

import ttsctl


class Response:
    headers = {"X-Audio-Duration": "1.25", "X-Sample-Rate": "16000"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return b"wav"


def main() -> None:
    health_checks = iter([OSError("offline"), {"ok": True}])
    def check_health(_url):
        result = next(health_checks)
        if isinstance(result, Exception):
            raise result
        return result
    started: list[tuple[bool, bool, bool]] = []
    with (
        patch.object(ttsctl, "request_json", side_effect=check_health),
        patch.object(ttsctl, "start_service", side_effect=lambda background, open_browser, local_daemon: started.append((background, open_browser, local_daemon))),
    ):
        ttsctl.ensure_service()
    assert started == [(True, False, True)]

    captured = []
    with patch.object(ttsctl.urllib.request, "urlopen", side_effect=lambda request, timeout: captured.append((request, timeout)) or Response()):
        wav, duration, sample_rate = ttsctl.request_audio("你好", 1.2)
    assert (wav, duration, sample_rate) == (b"wav", 1.25, 16000)
    assert json.loads(captured[0][0].data) == {"text": "你好", "speed": 1.2}
    print("ttsctl daemon checks ok")


if __name__ == "__main__":
    main()
