# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

`local-tts-service` 把 `sherpa-onnx + matcha-icefall-zh-en` 双语模型封装成常驻本地 HTTP 服务，供 Obsidian 插件、Codex hooks、Claude Code hooks 或其他本机工具调用，朗读文本不出本机。它是上层 git 仓库 `07codex_default`（Cloud TTS Reader Obsidian 插件）的子项目；兄弟目录 `matcha-demo` 存放模型文件（Docker build 脚本从这里拷模型进镜像）。

特性：Docker 一键部署（模型打进镜像，离线可用）、API Key 鉴权 + 调用记录、中文管理页、磁盘自清洁。

技术栈约束：
- Python 3，依赖 `sherpa-onnx==1.13.3` / `soundfile==0.14.0` / `huggingface-hub==1.21.0`。
- HTTP 层只用标准库 `http.server.ThreadingHTTPServer`，**不引入 Flask/FastAPI**。新增接口手写在 `Handler.do_GET` / `do_POST` / `do_DELETE` 的 `if p == ...` 链。
- 持久化用 **SQLite**（`sqlite3` 标准库），WAL 模式，全局锁串行化。
- 鉴权用标准库原语：`secrets` / `hashlib` / `hmac.compare_digest`。

## 常用命令

Windows 11 + PowerShell 7。

**Docker 一键**（推荐，生产形态）：
```powershell
.\scripts\build_windows.ps1     # 拷模型 → docker build → compose up → 打印首次凭证
docker compose logs -f tts
docker compose down
docker compose up -d --build    # 改代码后重建
```

**本地开发**（venv，模型走 `../matcha-demo`）：
```powershell
.\scripts\setup_windows.ps1
.\.venv\Scripts\python.exe .\server.py --data-dir .data --open
```
开发时可指定 `--data-dir` / `--host` / `--port`；环境变量 `TTS_HOST` / `TTS_PORT` / `TTS_REQUIRE_AUTH` / `TTS_CLEANUP_DAYS` / `TTS_DATA_DIR` 覆盖配置。

**冒烟测试**：
```bash
curl http://127.0.0.1:51273/api/health
curl -X POST http://127.0.0.1:51273/api/synthesize -H "X-API-Key: <key>" -H "Content-Type: application/json" -d "{\"text\":\"你好\"}" --output out.wav
```

无自动化测试。鉴权 / 合成 / 管理链路用 curl 或管理页手动验证。

## 架构

### 模块划分

| 文件 | 职责 |
|---|---|
| `server.py` | HTTP Handler（路由 + 鉴权中间件）、配置管理、启动流程、清理后台线程 |
| `tts_engine.py` | `TtsEngine`：OfflineTts 懒加载与按配置缓存（抽自 server.py） |
| `db.py` | SQLite 连接、建表、WAL、全局锁、`query` / `execute` |
| `auth.py` | 管理员登录、session cookie、API Key 增删查验 |
| `usage.py` | 调用记录写入 / 汇总 / 清理、磁盘占用统计 |
| `static/index.html` + `static/app.js` | 中文三 tab 单页（试听 / 配置 / 接入管理） |

### 鉴权分层

- `/api/synthesize`、`/api/say`：要求 **API Key**（`X-API-Key` 或 `Authorization: Bearer`）。`Handler._authenticate_api_key` 校验，返回 `(ok, key_id)`。
- `/api/config`、`/api/admin/*`：要求**管理员 session cookie**（`session=<user>:<exp>:<sig>`，HMAC 签名）。`Handler._require_admin` 校验。
- `/api/health`、静态文件：免鉴权。
- `require_auth=False` 时合成放行（仅本机调试）。

session cookie 必须用**单个**名为 `session` 的 cookie 携带 `user:exp:sig`——把 exp/sig 写成 Set-Cookie 属性会被浏览器丢弃、回传只剩 user（曾踩坑）。见 `auth.make_session_cookie`。

### 模型缓存键（tts_engine.py）

`TtsEngine._key` = `(model_dir, vocoder, threads, noise_scale, length_scale, silence_scale, max_num_sentences)`。这 7 项任一变化才重建 OfflineTts；**`speed` 不在键里**，按请求传入，改语速不重载。判断"改某参数会不会重载模型"就看它在不在这个元组里。

模型目录需含：`model-steps-3.onnx`、`lexicon.txt`、`tokens.txt`、`espeak-ng-data/`、`phone-zh.fst` / `date-zh.fst` / `number-zh.fst`。`validate()` 失败抛 RuntimeError。

### 配置

- `data/config.json`（运行期）。**不存 `data_dir`**——避免"config 在 data_dir 下又要靠 data_dir 找"的循环依赖；`data_dir` 由 `--data-dir` / `TTS_DATA_DIR` / 默认 `ROOT/data` 决定，启动后固定，API 仅 expose 只读字符串。
- `normalize_config` 钳制所有数值（threads∈[1,16]、speed∈[0.5,2]、noise∈[0.1,2]、length∈[0.5,2]、silence∈[0,2]、max_sentences∈[1,20]、cleanup_days∈[1,365]）。新增配置项必须在此登记上下限，并同步 `config.example.json` 与 `static/app.js` 的 `CONFIG_KEYS` / `NUM_KEYS` 与 `index.html` 表单。
- host/port 改 config 需**重启**才生效（`serve_forever` 启动时读一次）。

### 时间戳

所有 DB 时间戳一律用 SQLite `datetime('now')`（格式 `YYYY-MM-DD HH:MM:SS`），**不要**用 Python `isoformat()`（带 `T` 和时区，与 `usage.cleanup` 的 `datetime('now','-N days')` 字符串比较会因分隔符不同判错）。

### 首次启动

`main()` → `db.init_db` → `auth.init_admin`（admin 表空时生成随机密码 + 默认 API Key，落盘 `first-run-credentials.txt` 并打印到 stdout）→ `get_or_create_session_secret` → 起清理线程 → `serve_forever`。

### 磁盘清理

`server._start_cleanup_thread` 起 daemon 线程：启动即清一次 `usage.cleanup(cleanup_days)`，之后每 24h 一次；每次循环重读 config 的 cleanup_days。线程内吞所有异常。页面 `POST /api/admin/cleanup` 手动触发。Docker 日志由 compose 配置 `10m × 3` 轮转。

## Docker

`Dockerfile`（`python:3.11-slim`）必须 apt 装 `libgomp1`（sherpa-onnx OpenMP）+ `libsndfile1`（soundfile 写 WAV），两者 wheel 都不带。`models/` 由 build 脚本从 `../matcha-demo` 拷入 build context，再 `COPY models/` 进镜像（离线可用，镜像 ~1.8-2GB）。`.dockerignore` **保留** `models/`，裁掉 `.venv` / `data` / `__pycache__`。

容器内监听 `0.0.0.0`（`TTS_HOST`），`data/` 挂卷持久化 SQLite 与凭证。

## 改动注意事项

- 新增 HTTP 接口：编辑 `Handler.do_GET` / `do_POST` / `do_DELETE` 的 `if p == ...` 链（`p = self._path_only()` 已去 query）。返回 JSON 用 `send_json`，敏感接口先 `_require_admin()` 或 `_authenticate_api_key()`。
- 新增配置参数：同步 5 处——`DEFAULT_CONFIG`、`normalize_config` 钳制、`config.example.json`、`index.html` 表单、`app.js` 的 `CONFIG_KEYS` / `NUM_KEYS`。漏一处出"前端能填后端忽略"。
- 升级 `sherpa-onnx`：先确认 `OfflineTtsMatchaModelConfig` / `OfflineTtsConfig` 字段名变化（`tts_engine._get_tts`）。
- 静态文件路由有路径穿越防护（`file_path.resolve()` 必须在 `STATIC_DIR` 下），新增文件类路由保留此检查。
