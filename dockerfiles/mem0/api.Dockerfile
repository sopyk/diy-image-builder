# Mem0 API 生产镜像
# 基于官方 server/Dockerfile，唯一改动：去掉 --reload（开发热重载）
# 构建上下文：上游仓库的 server/ 目录
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# 官方: CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
# 生产去掉 --reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
