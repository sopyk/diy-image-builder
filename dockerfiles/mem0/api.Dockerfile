# Mem0 API 生产镜像（diy-image-builder 自定义版）
# 构建上下文：上游仓库的 server/ 目录
#
# 相对官方 server/Dockerfile（python:3.12-slim）的必要改动：
#   1) 安装 libpq5 —— 官方生产 Dockerfile 疏漏：requirements 装纯 psycopg
#      （非 binary），slim 不含 libpq，缺它启动即报
#      "no pq wrapper available / libpq library not found"。
#      （官方 dev.Dockerfile 用完整 python:3.12 自带 libpq，所以 dev 能跑）
#   2) 打入 patch-main.sh：支持 LLM / embedder 分别用环境变量指定
#      OpenAI 兼容 base_url（MEM0_LLM_BASE_URL / MEM0_EMBEDDER_BASE_URL），
#      上游只支持共用一个 OPENAI_BASE_URL，无法 LLM 走云端 + embedder 走本地。
#   3) CMD 去掉 --reload（开发热重载）。
FROM python:3.12-slim

WORKDIR /app

# psycopg 运行时依赖 libpq5
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 打入自定义启动补丁（patch-main.sh 由 workflow 从 diy-image-builder 复制进来）
COPY patch-main.sh /usr/local/bin/patch-main.sh
RUN chmod +x /usr/local/bin/patch-main.sh && /usr/local/bin/patch-main.sh

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# 启动时先确保补丁就位（幂等），再起服务；生产无 --reload
CMD ["sh", "-c", "/usr/local/bin/patch-main.sh && uvicorn main:app --host 0.0.0.0 --port 8000"]
