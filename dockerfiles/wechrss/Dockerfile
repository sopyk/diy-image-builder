# WeRSS（johamwon/wechrss）DIY 构建文件
#
# 与上游原版 Dockerfile 的差异：
#   1) 不装 Playwright/Chromium（省 ~600 MB）。
#      依据：article_identity.py 的 _resolve_with_browser() 是函数内延迟 import，
#      只在 HTTP 解析不到公众号 BID 时才走浏览器兜底；扫码 / 订阅 / 同步 / 出 feed 都不需要。
#      真需要浏览器时，打 --build-arg INSTALL_CHROMIUM=1。
#   2) 补装 tzdata —— slim 基础镜像默认没有 zoneinfo，缺了 TZ=Asia/Shanghai 不生效，
#      文章发布时间会整体偏 8 小时。
#
# 构建上下文 = 上游源码根目录，本文件由 workflow 拷贝进源码树后再 build。

FROM python:3.12-slim

ARG INSTALL_CHROMIUM=0

LABEL org.opencontainers.image.title="WeRSS" \
      org.opencontainers.image.description="Self-hosted WeChat public account to RSS service (DIY build, no Chromium by default)" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=Asia/Shanghai

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN if [ "$INSTALL_CHROMIUM" = "1" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends libatomic1 \
        && rm -rf /var/lib/apt/lists/* \
        && python -m playwright install --with-deps chromium ; \
    fi

COPY . .
RUN mkdir -p /app/data

EXPOSE 8080 7860
HEALTHCHECK --interval=30s --timeout=8s --start-period=20s --retries=3 \
    CMD ["python", "scripts/healthcheck.py"]

CMD ["sh", "-c", "python web_app.py --host 0.0.0.0 --port ${PORT:-8080}"]
