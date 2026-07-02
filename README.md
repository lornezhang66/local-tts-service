# Local TTS Service

把 `sherpa-onnx + matcha-icefall-zh-en` 双语模型封装成**本地常驻 HTTP 服务**，自带 API Key 鉴权与调用记录，朗读文本不出本机。供 Obsidian、Codex hooks、Claude Code hooks 或其他本机工具调用。

## 特性

- **一键 Docker 部署**：模型打进镜像，完全离线可用，`docker compose up -d` 即跑。
- **API Key 鉴权**：为每个客户端颁发独立密钥，可启停 / 删除，合成接口必须带 key。
- **调用记录**：每次合成记录文本长度、音频时长、耗时、成功 / 失败，按 key 汇总，可观测。
- **中文管理页**：试听 / 配置 / 接入管理 三页，全中文。
- **磁盘自清洁**：调用记录按天自动清理，Docker 日志轮转，不产生数据垃圾。
- 文本只进内存合成，不落盘临时文件。

## 一键部署（Docker，推荐）

前提：已安装 Docker Desktop。模型从兄弟目录 `matcha-demo` 拷入（本机已下好）。

Windows PowerShell：

```powershell
cd local-tts-service
.\scripts\build_windows.ps1
```

macOS：

```bash
cd local-tts-service
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

脚本会：拷贝模型 → 构建镜像 → 启动容器 → 打印**首次启动凭证**（管理员用户名 / 密码、默认 API Key），同时写入 `data/first-run-credentials.txt`。

启动后打开 http://127.0.0.1:8787，右上角登录后即可管理。

后续命令：

```bash
docker compose logs -f tts     # 看日志
docker compose down            # 停止（data/ 数据保留）
docker compose up -d --build   # 改代码后重建
```

## CLI

本服务的本机入口是 `ttsctl`。Windows 使用 `ttsctl.ps1`，macOS 使用 `ttsctl.sh`。

Windows：

```powershell
.\ttsctl.ps1 install
.\ttsctl.ps1 start --background
.\ttsctl.ps1 status
.\ttsctl.ps1 hooks install
.\ttsctl.ps1 test
```

macOS：

```bash
chmod +x ttsctl.sh
./ttsctl.sh install
./ttsctl.sh start --background
./ttsctl.sh status
./ttsctl.sh hooks install
./ttsctl.sh test
```

常用命令：

| 命令 | 作用 |
|---|---|
| `install` | 安装 Python 依赖并下载模型 |
| `start` | 前台启动服务 |
| `start --background` | 后台启动服务并写入 pid |
| `stop` | 停止由 `start --background` 启动的服务 |
| `status` | 检查 HTTP 服务和 Agent hooks 状态 |
| `test` | 用 hooks API Key 调用合成接口并保存测试 wav |
| `hooks install` | 自动合并 Codex / Claude Code 朗读 hooks |
| `hooks uninstall` | 移除 Codex / Claude Code 朗读 hooks |
| `hooks status` | 查看 hooks 是否已安装 |

## 非 Docker 本地开发

```powershell
cd local-tts-service
.\scripts\setup_windows.ps1    # 建 venv、装依赖、下模型、生成 config
.\scripts\run_windows.ps1      # 启动
```

## HTTP 接口

合成接口需 API Key（`X-API-Key` 或 `Authorization: Bearer <key>`）：

```bash
curl -X POST http://127.0.0.1:8787/api/synthesize \
  -H "X-API-Key: tts-xxxx" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"你好\",\"speed\":1.0}" --output out.wav
```

`/api/say` 是 `/api/synthesize` 的别名。响应头带 `X-Audio-Duration`（秒）、`X-Sample-Rate`。

健康检查（免鉴权）：`GET /api/health`

管理接口（管理员 session cookie 鉴权，浏览器里操作即可）：API Key 增删、调用记录查看、配置修改、磁盘清理。

## 接入管理页面

浏览器打开服务地址 → 右上角登录（管理员密码）→ 切到「接入管理」tab：

- 新建 / 启停 / 删除 API Key（明文仅创建时显示一次，可选填入试听框）。
- 调用记录：按 key 汇总卡片 + 最近明细表。
- 磁盘状态：`data/` 占用、记录条数，一键清理过期记录。

## Agent 钩子集成

服务内置 Codex / Claude Code hook 适配层，脚本在 `hooks/`。

Windows 一键安装：

```powershell
.\ttsctl.ps1 hooks install
```

macOS 一键安装：

```bash
chmod +x ttsctl.sh hooks/agent-tts-hook.sh
./ttsctl.sh hooks install
```

安装脚本会：

- 从 `data/first-run-credentials.txt` 读取默认 API Key，并写入被 `.gitignore` 忽略的 `hooks/config.json`。
- 合并 Codex hooks 到 `~/.codex/hooks.json`。
- 合并 Claude Code hooks 到 `~/.claude/settings.json`。
- 安装前自动备份原配置。

默认只朗读短提醒：

- `SessionStart`
- `PermissionRequest`
- `Notification`
- `Stop`

不会朗读每个工具调用，避免噪音。Codex 如提示 hook 需要 review/trust，在 Codex 中执行 `/hooks` 后信任本服务 hook。

## 配置

`data/config.json`（运行期，页面可改）。主要参数：

- `host` / `port`：监听地址（改后需重启）。
- `model_dir` / `vocoder`：模型路径。
- `threads` / `speed` / `noise_scale` / `length_scale` / `silence_scale` / `max_num_sentences`：合成参数。
- `cleanup_days`：调用记录保留天数，默认 30。
- `require_auth`：合成鉴权开关，默认开。

环境变量覆盖（Docker 友好）：`TTS_HOST` / `TTS_PORT` / `TTS_REQUIRE_AUTH` / `TTS_CLEANUP_DAYS` / `TTS_DATA_DIR`。

## 磁盘清理

| 垃圾源 | 处理 |
|---|---|
| 调用记录 | 后台线程每天按 `cleanup_days` 清理；页面可手动触发 |
| Docker 日志 | compose 限 `10m × 3` 轮转 |
| 模型 | 打进镜像，不增长 |
| 合成音频 | 内存生成，不落盘 |

`data/` 目录只含：`tts.db`、`config.json`、`session_secret.txt`、`first-run-credentials.txt`。

## 隐私

本地 Matcha 后端：朗读文本只进内存，合成后不落盘，不出本机。API Key、管理员密码以摘要 / 哈希形式存本地 SQLite，明文密码不存储。
