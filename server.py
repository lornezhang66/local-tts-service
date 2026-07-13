"""本地 TTS HTTP 服务。

两层鉴权：
- 合成接口（/api/synthesize、/api/say）要求 API Key（X-API-Key 或 Bearer）。
- 管理接口（/api/config、/api/admin/*）要求管理员 session cookie。
持久化用 SQLite（见 db.py），HTTP 层用标准库 http.server，不引入第三方框架。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import auth
import db
import usage
from tts_engine import ENGINE, ROOT, resolve_path

STATIC_DIR = ROOT / "static"

DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 51273,
    "model_dir": "models/matcha-icefall-zh-en",
    "vocoder": "models/vocos-16khz-univ.onnx",
    "threads": 6,
    "speed": 1.0,
    "noise_scale": 0.667,
    "length_scale": 1.0,
    "silence_scale": 0.2,
    "max_num_sentences": 1,
    "cleanup_days": 30,
    "require_auth": True,
}

# 运行期状态，由 main() 在启动时设置。data_dir 不写入 config（避免"config 存在
# data_dir 下、又要靠 data_dir 找 config"的循环依赖），改由 env/参数/默认值决定，
# 启动后固定；config 里仅 expose 只读字符串给前端展示。
_data_dir: Path = ROOT / "data"
_session_secret: str = ""
_require_auth: bool = True


class Handler(SimpleHTTPRequestHandler):
    server_version = "LocalTtsService/2.0"

    # ---------- 鉴权 ----------

    def _path_only(self) -> str:
        return self.path.split("?", 1)[0]

    def _is_admin(self) -> bool:
        return (
            auth.parse_session_cookie(self.headers.get("Cookie"), _session_secret) is not None
        )

    def _require_admin(self) -> bool:
        """未登录返回 False 且已发 401；已登录返回 True。"""
        if self._is_admin():
            return True
        self.send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
        return False

    def _extract_api_key(self) -> str:
        key = self.headers.get("X-API-Key") or ""
        if not key:
            authz = self.headers.get("Authorization", "")
            if authz.lower().startswith("bearer "):
                key = authz[7:].strip()
        return key

    def _authenticate_api_key(self) -> tuple[bool, int | None]:
        """返回 (放行, key_id)。不放行时已发 401。

        require_auth=False 时直接放行：带 key 则记录对应 key_id，无 key 记匿名（None）。
        """
        if not _require_auth:
            key = self._extract_api_key()
            return True, (auth.verify_api_key(key) if key else None)
        key = self._extract_api_key()
        key_id = auth.verify_api_key(key) if key else None
        if key_id is None:
            self.send_json(
                {"error": "invalid or missing api key"}, status=HTTPStatus.UNAUTHORIZED
            )
            return False, None
        return True, key_id

    # ---------- GET ----------

    def do_GET(self) -> None:
        p = self._path_only()
        if p == "/api/health":
            self.send_json({"ok": True, "protocol": 1})
            return

        if p == "/api/config":
            if not self._require_admin():
                return
            cfg = load_config()
            cfg["data_dir"] = str(_data_dir)
            self.send_json(cfg)
            return

        if p == "/api/admin/keys":
            if not self._require_admin():
                return
            self.send_json({"keys": auth.list_api_keys()})
            return

        if p == "/api/admin/usage":
            if not self._require_admin():
                return
            self.send_json(
                {"summary": usage.summary(), "recent": usage.recent(100), "count": usage.count()}
            )
            return

        if p == "/api/admin/disk":
            if not self._require_admin():
                return
            self.send_json(
                {
                    "data_dir": str(_data_dir),
                    "bytes": usage.data_size(_data_dir),
                    "usage_count": usage.count(),
                }
            )
            return

        # 静态文件：根路径映射 index.html，沿用路径穿越防护。
        rel = "/index.html" if p == "/" else p
        file_path = (STATIC_DIR / rel.lstrip("/")).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_file(file_path)

    # ---------- POST ----------

    def do_POST(self) -> None:
        p = self._path_only()

        if p == "/api/admin/login":
            body = self.read_json()
            username = str(body.get("username", ""))
            if auth.verify_admin(username, str(body.get("password", ""))):
                self.send_json(
                    {"ok": True, "username": username},
                    extra_headers={
                        "Set-Cookie": auth.make_session_cookie(username, _session_secret)
                    },
                )
            else:
                self.send_json(
                    {"error": "invalid credentials"}, status=HTTPStatus.UNAUTHORIZED
                )
            return

        if p == "/api/admin/logout":
            # Max-Age=0 立即清除 cookie。
            self.send_json(
                {"ok": True},
                extra_headers={"Set-Cookie": "user=; Path=/; Max-Age=0"},
            )
            return

        if p == "/api/config":
            if not self._require_admin():
                return
            patch = self.read_json()
            config = normalize_config({**load_config(), **patch})
            save_config(config)
            config["data_dir"] = str(_data_dir)
            self.send_json(config)
            return

        if p == "/api/admin/keys":
            if not self._require_admin():
                return
            body = self.read_json()
            name = str(body.get("name", "新建 Key"))
            plain, key_id = auth.create_api_key(name)
            self.send_json(
                {"id": key_id, "key": plain, "name": name, "note": "明文仅此一次，请立即复制"}
            )
            return

        if p.startswith("/api/admin/keys/") and p.endswith("/toggle"):
            if not self._require_admin():
                return
            key_id = _parse_key_id(p)
            if key_id is None:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            body = self.read_json()
            auth.set_key_enabled(key_id, bool(body.get("enabled", True)))
            self.send_json({"ok": True})
            return

        if p.startswith("/api/admin/keys/") and p.endswith("/rename"):
            if not self._require_admin():
                return
            key_id = _parse_key_id(p)
            if key_id is None:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            body = self.read_json()
            auth.rename_key(key_id, str(body.get("name", "")))
            self.send_json({"ok": True})
            return

        if p == "/api/admin/cleanup":
            if not self._require_admin():
                return
            days = int(load_config().get("cleanup_days", 30))
            deleted = usage.cleanup(days)
            self.send_json({"deleted": deleted, "bytes": usage.data_size(_data_dir)})
            return

        if p in {"/api/synthesize", "/api/say"}:
            self._handle_synthesize()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    # ---------- DELETE ----------

    def do_DELETE(self) -> None:
        p = self._path_only()
        if p.startswith("/api/admin/keys/"):
            if not self._require_admin():
                return
            key_id = _parse_key_id(p)
            if key_id is None:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            auth.delete_key(key_id)
            self.send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    # ---------- 合成 ----------

    def _handle_synthesize(self) -> None:
        ok, key_id = self._authenticate_api_key()
        if not ok:
            return
        body = self.read_json()
        config = normalize_config({**load_config(), **body.get("config", {})})
        text = str(body.get("text", ""))
        speed = float(body["speed"]) if "speed" in body else None

        start = time.time()
        try:
            wav, duration, sample_rate = ENGINE.synthesize(text=text, config=config, speed=speed)
        except Exception as exc:  # noqa: BLE001 - 合成失败要记录并返回 400，不能让进程崩
            latency = int((time.time() - start) * 1000)
            usage.log_call(key_id, len(text), None, latency, "error", str(exc))
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        latency = int((time.time() - start) * 1000)
        usage.log_call(key_id, len(text), duration, latency, "ok")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.send_header("X-Audio-Duration", f"{duration:.3f}")
        self.send_header("X-Sample-Rate", str(sample_rate))
        self.end_headers()
        self.wfile.write(wav)

    # ---------- 基础工具 ----------

    def _serve_file(self, file_path: Path) -> None:
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def read_json(self) -> dict[str, Any]:
        # Content-Length 缺失/非数字时按空 body 处理，JSON 解析失败也返回空 dict，
        # 由调用方按字段缺失语义处理，避免恶意 body 让进程抛异常。
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def _parse_key_id(path: str) -> int | None:
    """从 /api/admin/keys/<id>[/action] 提取 id。"""
    parts = path.strip("/").split("/")
    try:
        return int(parts[3])
    except (IndexError, ValueError):
        return None


# ---------- 配置 ----------

def load_config() -> dict[str, Any]:
    path = _data_dir / "config.json"
    if not path.exists():
        save_config(DEFAULT_CONFIG)
    return normalize_config(json.loads(path.read_text(encoding="utf-8")))


def save_config(config: dict[str, Any]) -> None:
    _data_dir.mkdir(parents=True, exist_ok=True)
    path = _data_dir / "config.json"
    path.write_text(
        json.dumps(normalize_config(config), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    next_config = {**DEFAULT_CONFIG, **config}
    next_config["port"] = int(next_config["port"])
    next_config["threads"] = max(1, min(int(next_config["threads"]), 16))
    next_config["speed"] = clamp(float(next_config["speed"]), 0.5, 2.0)
    next_config["noise_scale"] = clamp(float(next_config["noise_scale"]), 0.1, 2.0)
    next_config["length_scale"] = clamp(float(next_config["length_scale"]), 0.5, 2.0)
    next_config["silence_scale"] = clamp(float(next_config["silence_scale"]), 0.0, 2.0)
    next_config["max_num_sentences"] = max(1, min(int(next_config["max_num_sentences"]), 20))
    next_config["cleanup_days"] = max(1, min(int(next_config["cleanup_days"]), 365))
    next_config["require_auth"] = bool(next_config["require_auth"])
    return next_config


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


# ---------- 清理后台线程 ----------

def _start_cleanup_thread() -> None:
    def loop() -> None:
        # 启动即清一次，之后每 24 小时一次。线程内吞所有异常，绝不拖垮主服务。
        # cleanup_days 每次循环重新读 config，便于运行期改值后下个周期生效。
        while True:
            try:
                days = int(load_config().get("cleanup_days", 30))
                deleted = usage.cleanup(days)
                if deleted:
                    print(f"[cleanup] 删除 {deleted} 条过期调用记录（>{days} 天）")
            except Exception as exc:  # noqa: BLE001 - 后台线程必须容错
                print(f"[cleanup] 失败: {exc}")
            time.sleep(86400)

    threading.Thread(target=loop, daemon=True, name="tts-cleanup").start()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def main() -> None:
    global _data_dir, _session_secret, _require_auth

    parser = argparse.ArgumentParser(description="本地 TTS HTTP 服务")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    parser.add_argument("--data-dir", dest="data_dir", help="数据目录（SQLite/凭证/配置）")
    args = parser.parse_args()

    _data_dir = Path(args.data_dir or os.environ.get("TTS_DATA_DIR") or (ROOT / "data")).resolve()
    _data_dir.mkdir(parents=True, exist_ok=True)

    db.init_db(_data_dir)
    creds = auth.init_admin(_data_dir / "first-run-credentials.txt")
    _session_secret = auth.get_or_create_session_secret(_data_dir / "session_secret.txt")

    config = load_config()
    config["host"] = args.host or os.environ.get("TTS_HOST") or config["host"]
    config["port"] = args.port or int(os.environ.get("TTS_PORT") or config["port"])
    _require_auth = _env_bool("TTS_REQUIRE_AUTH", bool(config.get("require_auth", True)))
    if "TTS_CLEANUP_DAYS" in os.environ:
        config["cleanup_days"] = int(os.environ["TTS_CLEANUP_DAYS"])
        save_config(config)

    if creds:
        print("=" * 64)
        print("首次启动凭证（也可在 data/first-run-credentials.txt 查看）")
        print(f"  管理用户名:   {creds['username']}")
        print(f"  管理密码:     {creds['password']}")
        print(f"  默认 API Key: {creds['default_key']}")
        print("请尽快登录管理页修改并妥善保管。")
        print("=" * 64)

    _start_cleanup_thread()

    httpd = ThreadingHTTPServer((config["host"], int(config["port"])), Handler)
    url = f"http://{config['host']}:{config['port']}"
    print(f"Local TTS Service: {url}  (auth={'on' if _require_auth else 'off'})")
    if args.open:
        webbrowser.open(url)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
