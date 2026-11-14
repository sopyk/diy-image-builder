# wechrss 全文补全中间层（自研，非上游项目）
#
# 作用：从 wechrss 的 feed 里取条目，用桌面 Chrome UA 抓 mp.weixin.qq.com 正文，
#       落 SQLite，再输出带 content:encoded 的全文 RSS 给下游 Agent。
# 源码：本目录 app.py（唯一权威版本，NAS 上不要再单独 build）。

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    DB_PATH=/app/data/fulltext.db \
    PORT=8083

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py
RUN mkdir -p /app/data

EXPOSE 8083
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8083/healthz', timeout=8).status == 200 else 1)"]

CMD ["python3", "-u", "app.py"]
