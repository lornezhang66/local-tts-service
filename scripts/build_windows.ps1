$ErrorActionPreference = "Stop"
# 本脚本：从兄弟目录 matcha-demo 拷模型进 build context → 构建镜像 → 启动容器
# 必须通过本脚本（或先手动准备 models/）再 docker build，Dockerfile 依赖 models/ 存在
$DOCKER   = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$DOCKER_COMPOSE = "C:\Program Files\Docker\Docker\resources\bin\docker-compose.exe"
if (!(Test-Path $DOCKER)) { throw "Docker 未安装，请先安装 Docker Desktop" }

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

New-Item -ItemType Directory -Force models | Out-Null
if (!(Test-Path "models/matcha-icefall-zh-en")) {
    Write-Host "拷贝 matcha-icefall-zh-en 模型到 models/（约 1.5GB，首次较慢）..."
    Copy-Item -Recurse "../matcha-demo/matcha-icefall-zh-en" "models/"
}
if (!(Test-Path "models/vocos-16khz-univ.onnx")) {
    Copy-Item "../matcha-demo/vocos-16khz-univ.onnx" "models/"
}

Write-Host "构建镜像 local-tts-service:latest ..."
& $DOCKER build -t local-tts-service:latest .

Write-Host "启动容器（docker compose up -d）..."
& $DOCKER_COMPOSE up -d

Write-Host "等待服务初始化并打印首次凭证..."
Start-Sleep -Seconds 5
& $DOCKER_COMPOSE logs --tail 14 tts

Write-Host ""
Write-Host "服务地址: http://127.0.0.1:51273"
Write-Host "管理页:   浏览器打开上面地址 → 右上角登录（用上面的管理员密码）→ 接入管理 创建/查看 API Key"
Write-Host "停服务:   C:\Program Files\Docker\Docker\resources\bin\docker-compose.exe down    （data/ 数据保留）"
