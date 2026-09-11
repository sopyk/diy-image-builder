# Mem0 API 生产镜像
# 基于官方 server/Dockerfile（python:3.12-slim），两处必要改动：
#   1) 安装 libpq5 —— 官方生产 Dockerfile 的疏漏：requirements 装的是纯 psycopg
#      （非 psycopg-binary），slim 镜像不含 libpq，缺它 API 启动即报
#      "no pq wrapper available / libpq library not found"。
#      （官方 dev.Dockerfile 基于完整 python:3.12 自带 libpq，所以 dev 能跑）
#   2) CMD 去掉 --reload（开发热重载）
# 构建上下文：上游仓库的 server/ 目录
FROM python:3.12-slim

WORKDIR /app

# psycopg 运行时依赖 libpq5
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# 官方: CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
# 生产去掉 --reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
