# python:3.11-slim 基于 Debian，需补两个系统库：
#   libgomp1   —— sherpa-onnx/onnxruntime 的 OpenMP 运行时（wheel 不带，缺则 import 报错）
#   libsndfile1 —— soundfile 写 WAV 依赖（PyPI wheel 不保证捆绑，slim 镜像默认无）
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用层缓存：依赖不变时改代码不会重装 sherpa-onnx
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py tts_engine.py db.py auth.py usage.py ./
COPY static/ ./static/
# 模型由 build 脚本预先拷入 build context 的 models/，打进镜像实现离线可用
COPY models/ ./models/

# 容器内对外监听 0.0.0.0；鉴权默认开启。host/port/鉴权/清理天数均可被 compose env 覆盖
ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=51273 \
    TTS_REQUIRE_AUTH=true

EXPOSE 51273
# data/ 挂载卷：SQLite、API Key 摘要、session secret、运行期配置、首启凭证
VOLUME ["/app/data"]

CMD ["python", "server.py"]
