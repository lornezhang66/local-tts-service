# Agent Hooks

这里放 Codex / Claude Code 的朗读 hook。它不实现 TTS 服务，只调用本目录已有服务：

```text
POST http://127.0.0.1:51273/api/synthesize
X-API-Key: tts-xxxx
```

## 配置

复制配置：

```powershell
Copy-Item hooks\config.example.json hooks\config.json
```

填入服务 API Key：

```json
{
  "service_url": "http://127.0.0.1:51273",
  "api_key": "tts-xxxx"
}
```

也可以用环境变量，不落盘：

```powershell
$env:LOCAL_TTS_API_KEY="tts-xxxx"
$env:LOCAL_TTS_SERVICE_URL="http://127.0.0.1:51273"
```

## 测试

```powershell
"{}" | powershell -NoProfile -ExecutionPolicy Bypass -File .\hooks\agent-tts-hook.ps1 --source codex --event Stop
```

## 策略

默认只播短提醒：

- `SessionStart`
- `PermissionRequest`
- `Notification`
- `Stop`

不播每个工具调用，避免噪音。
