#!/usr/bin/env bash
# 从兄弟目录 matcha-demo 拷模型进 build context → 构建镜像 → 启动容器
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p models
if [ ! -d "models/matcha-icefall-zh-en" ]; then
  echo "拷贝 matcha-icefall-zh-en 模型到 models/（约 1.5GB，首次较慢）..."
  cp -R "../matcha-demo/matcha-icefall-zh-en" "models/"
fi
if [ ! -f "models/vocos-16khz-univ.onnx" ]; then
  cp "../matcha-demo/vocos-16khz-univ.onnx" "models/"
fi

echo "构建镜像 local-tts-service:latest ..."
docker build -t local-tts-service:latest .

echo "启动容器（docker compose up -d）..."
docker compose up -d

echo "等待服务初始化并打印首次凭证..."
sleep 5
docker compose logs --tail 14 tts

echo ""
echo "服务地址: http://127.0.0.1:8787"
echo "管理页:   浏览器打开上面地址 → 右上角登录 → 接入管理 创建/查看 API Key"
echo "停服务:   docker compose down    （data/ 数据保留）"
