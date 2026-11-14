#!/usr/bin/env python3
"""
wechrss 全文补全中间层（微信特化，单文件）

做什么：
  订阅 wechrss 的 /feeds/<id>.xml -> 带桌面浏览器 UA 拉取 mp.weixin.qq.com 正文
  -> 清洗后存入 SQLite「正文库」-> 重新输出带 content:encoded 的 RSS 给下游 Agent。

设计原则：
  - 完全不改 wechrss 源码，两个容器独立，随时可以停用中间层回到原始 feed。
  - 克制抓取：串行 + 每篇间隔 + 失败指数退避；不做验证码绕过、不做代理轮换、不高频重试。
  - 遇到风控页必须显式判失败，绝不把 18KB 的验证码页当正文缓存（HTTP 200 静默污染）。

环境变量见 README.md。
"""
from __future__ import annotations

import base64
import hmac
import html
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, jsonify, request

# ---------------------------------------------------------------- 配置
def env(k: str, d: str = "") -> str:
    return os.environ.get(k, d)


def env_int(k: str, d: int) -> int:
    try:
        return int(os.environ.get(k, d))
    except ValueError:
        return d


UPSTREAM_BASE = env("UPSTREAM_BASE", "http://wechrss:8080").rstrip("/")
UPSTREAM_USER = env("UPSTREAM_USER", "admin")          # wechrss 固定用户名
UPSTREAM_PASSWORD = env("UPSTREAM_PASSWORD", "")       # = wechrss 的 ADMIN_PASSWORD
AUTO_DISCOVER = env("AUTO_DISCOVER", "1") == "1"       # 自动发现新增公众号
SOURCE_IDS = [s.strip() for s in env("SOURCE_IDS", "").split(",") if s.strip()]
POLL_INTERVAL = env_int("POLL_INTERVAL", 1800)         # 轮询上游间隔（秒）
FETCH_DELAY = env_int("FETCH_DELAY", 3)                # 每篇正文之间的间隔（秒）
MAX_PER_RUN = env_int("MAX_PER_RUN", 10)               # 单轮最多抓几篇
MAX_ATTEMPTS = env_int("MAX_ATTEMPTS", 3)              # 单篇最多尝试几次
HTTP_TIMEOUT = env_int("HTTP_TIMEOUT", 20)
DB_PATH = env("DB_PATH", "/app/data/fulltext.db")
PUBLIC_BASE = env("PUBLIC_BASE", "http://127.0.0.1:8083").rstrip("/")
PORT = env_int("PORT", 8083)
BASIC_USER = env("BASIC_USER", "")                     # 中间层自身可选认证，默认关
BASIC_PASS = env("BASIC_PASS", "")

# 与 wechrss 的 BROWSER_UA 保持一致：桌面 Chrome，实测可拿到完整正文
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
CHALLENGE_MARKERS = (
    "当前环境异常", "完成验证后即可继续访问", "访问过于频繁", "操作频繁",
    "wappoc_appmsgcaptcha",
)
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

logging.basicConfig(
    level=env("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("fulltext")

app = Flask(__name__)


# ---------------------------------------------------------------- 正文库
SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    guid         TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    source_name  TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    link         TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    pub_date     TEXT NOT NULL DEFAULT '',
    content_html TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    error        TEXT NOT NULL DEFAULT '',
    next_retry   INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    fetched_at   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status, next_retry);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id, created_at DESC);
"""


def db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with db() as c:
        c.executescript(SCHEMA)


def save_items(items: list[dict], source_id: str, source_name: str) -> int:
    """上游条目入库。已有正文不覆盖；若上游补全了原文链接，则重置为待抓。"""
    now = int(time.time())
    n = 0
    with db() as c:
        for it in items:
            c.execute(
                """
                INSERT INTO articles (guid, source_id, source_name, title, link,
                                      summary, pub_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guid) DO UPDATE SET
                    title       = excluded.title,
                    source_name = excluded.source_name,
                    summary     = excluded.summary,
                    pub_date    = excluded.pub_date,
                    link        = CASE WHEN articles.content_html = '' AND articles.link != excluded.link
                                       THEN excluded.link ELSE articles.link END,
                    status      = CASE WHEN articles.content_html = '' AND articles.link != excluded.link
                                       THEN 'pending' ELSE articles.status END,
                    next_retry  = CASE WHEN articles.content_html = '' AND articles.link != excluded.link
                                       THEN 0 ELSE articles.next_retry END
                """,
                (it["guid"], source_id, source_name, it["title"], it["link"],
                 it["summary"], it["pub_date"], now),
            )
            n += 1
    return n


# ---------------------------------------------------------------- 上游
def upstream_auth():
    return (UPSTREAM_USER, UPSTREAM_PASSWORD) if UPSTREAM_PASSWORD else None


def discover_sources() -> list[tuple[str, str]]:
    """每轮重新拉 /api/sources，加新公众号后无需改配置、无需重启。"""
    if not AUTO_DISCOVER:
        return [(s, s) for s in SOURCE_IDS]
    try:
        r = requests.get(f"{UPSTREAM_BASE}/api/sources", auth=upstream_auth(),
                         timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        rows = data if isinstance(data, list) else data.get("sources", [])
        out = []
        for s in rows:
            sid = str(s.get("id", "")).strip()
            if sid:
                out.append((sid, str(s.get("name") or s.get("mp_name") or sid)))
        if out:
            return out
        log.warning("/api/sources 返回空列表")
    except Exception as e:
        log.warning("自动发现来源失败: %s", e)
    return [(s, s) for s in SOURCE_IDS]


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for node in root.findall("./channel/item"):
        def text(tag: str) -> str:
            el = node.find(tag)
            return (el.text or "").strip() if el is not None else ""

        link, title = text("link"), text("title")
        if not link.startswith(("http://", "https://")):
            continue
        out.append({
            "guid": text("guid") or link,
            "title": title,
            "link": link,
            "summary": text("description"),
            "pub_date": text("pubDate"),
        })
    return out


def fetch_upstream() -> int:
    total = 0
    for sid, name in discover_sources():
        try:
            r = requests.get(f"{UPSTREAM_BASE}/feeds/{sid}.xml",
                             auth=upstream_auth(), timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            items = parse_feed(r.content)
            save_items(items, sid, name)
            log.info("源 %s(%s): %d 条", sid, name, len(items))
            total += len(items)
        except Exception as e:
            log.warning("读取源 %s 的 feed 失败: %s", sid, e)
    return total


# ---------------------------------------------------------------- 抓正文
class Blocked(RuntimeError):
    """命中风控 / 验证码页 / 无正文容器 —— 不得缓存为正文。"""


def extract_article(url: str) -> str:
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://mp.weixin.qq.com/",
    }
    r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    # 微信页面固定 UTF-8。部分验证码页不声明 charset，requests 会猜成 ISO-8859-1，
    # 中文风控文案变乱码会漏判；显式指定后也供 BeautifulSoup 正确解析正文。
    r.encoding = "utf-8"
    text = r.text
    size = len(r.content)

    # 1) 验证码页：HTTP 200、约 18KB、无正文容器，必须显式拦下
    if "wappoc_appmsgcaptcha" in r.url:
        raise Blocked(f"重定向到验证码页 ({size} B)")
    if any(m in text for m in CHALLENGE_MARKERS):
        raise Blocked(f"命中风控文案 ({size} B)")

    soup = BeautifulSoup(text, "lxml")
    content = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
    if content is None:
        raise Blocked(f"页面中无 #js_content ({size} B)")

    # 2) 微信把正文容器默认设为 visibility:hidden / opacity:0，靠 JS 显示。
    #    RSS 里没有 JS，不剥掉这两个样式下游会看到一片空白。
    style = content.get("style", "") or ""
    style = re.sub(r"visibility\s*:\s*hidden\s*;?", "", style, flags=re.I)
    style = re.sub(r"opacity\s*:\s*0(?:[.;]|$)", "", style, flags=re.I)
    if style.strip(" ;"):
        content["style"] = style.strip(" ;")
    else:
        content.attrs.pop("style", None)

    for node in content.select("script, style, iframe, object, embed, form, noscript"):
        node.decompose()
    for node in content.find_all(True):
        for attr in list(node.attrs):
            if attr.lower().startswith("on"):
                del node.attrs[attr]
        for attr in ("href", "src"):
            v = node.get(attr)
            if isinstance(v, str) and v.strip().lower().startswith("javascript:"):
                del node.attrs[attr]

    for img in content.select("img"):
        # 微信正文图片是 data-src 懒加载，且 mmbiz.qpic.cn 有防盗链
        ds = img.get("data-src") or img.get("data-original")
        if ds and not img.get("src"):
            img["src"] = ds
        img["referrerpolicy"] = "no-referrer"
        img["loading"] = "lazy"

    result = str(content)
    if len(result) < 200:
        raise Blocked(f"正文过短 ({len(result)} B)，疑似异常页面")
    return result


def backoff(attempts: int) -> int:
    return min(3600, 300 * (2 ** max(0, attempts - 1)))


def fetch_pending() -> tuple[int, int]:
    now = int(time.time())
    with db() as c:
        todo = c.execute(
            "SELECT * FROM articles WHERE status='pending' AND next_retry<=? "
            "AND attempts<? ORDER BY created_at DESC LIMIT ?",
            (now, MAX_ATTEMPTS, MAX_PER_RUN),
        ).fetchall()
    ok = fail = 0
    for row in todo:
        try:
            body = extract_article(row["link"])
            with db() as c:
                c.execute(
                    "UPDATE articles SET content_html=?, status='ok', error='', "
                    "fetched_at=? WHERE guid=?",
                    (body, int(time.time()), row["guid"]),
                )
            ok += 1
            log.info("全文 OK  %s  %s", row["guid"], row["title"][:40])
        except Exception as e:
            attempts = row["attempts"] + 1
            exhausted = attempts >= MAX_ATTEMPTS
            kind = "blocked" if isinstance(e, Blocked) else "error"
            # 未到上限时保持 pending，靠 next_retry 退避后自动重试；到上限才落为
            # blocked/error 等人工 POST /retry，避免失败一次就永久卡住。
            status = kind if exhausted else "pending"
            with db() as c:
                c.execute(
                    "UPDATE articles SET status=?, attempts=?, error=?, next_retry=? WHERE guid=?",
                    (status, attempts, str(e)[:300], int(time.time()) + backoff(attempts), row["guid"]),
                )
            fail += 1
            log.warning("全文失败 %s (%d/%d)%s %s: %s", kind, attempts, MAX_ATTEMPTS,
                        " 停止重试" if exhausted else " 将退避重试", row["guid"], str(e)[:100])
        time.sleep(FETCH_DELAY)
    return ok, fail


def poll_loop() -> None:
    while True:
        try:
            n = fetch_upstream()
            ok, fail = fetch_pending()
            log.info("本轮完成: 上游 %d 条 / 新抓 %d 篇 / 失败 %d 篇", n, ok, fail)
        except Exception:
            log.exception("轮询异常")
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------- 输出
def render_feed(rows: list[sqlite3.Row], title: str, self_url: str,
                only_full: bool = False) -> bytes:
    ET.register_namespace("content", CONTENT_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = self_url
    ET.SubElement(ch, "description").text = "wechrss + fulltext proxy (content:encoded)"
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    for r in rows:
        if only_full and r["status"] != "ok":
            continue
        item = ET.SubElement(ch, "item")
        ET.SubElement(item, "title").text = r["title"] or "(无标题)"
        ET.SubElement(item, "link").text = r["link"]
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = r["guid"]
        if r["pub_date"]:
            ET.SubElement(item, "pubDate").text = r["pub_date"]
        ET.SubElement(item, "description").text = r["summary"] or ""
        if r["status"] == "ok" and r["content_html"]:
            ET.SubElement(item, f"{{{CONTENT_NS}}}encoded").text = r["content_html"]
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def query_rows(source_id: str | None, limit: int) -> list[sqlite3.Row]:
    with db() as c:
        if source_id:
            return c.execute(
                "SELECT * FROM articles WHERE source_id=? ORDER BY created_at DESC LIMIT ?",
                (source_id, limit),
            ).fetchall()
        return c.execute(
            "SELECT * FROM articles ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


@app.before_request
def guard():
    if not BASIC_USER:
        return None
    h = request.headers.get("Authorization", "")
    if not h.startswith("Basic "):
        return Response("Unauthorized", 401,
                        {"WWW-Authenticate": 'Basic realm="fulltext"'})
    try:
        raw = base64.b64decode(h.split(" ", 1)[1]).decode()
        u, p = raw.split(":", 1)
    except Exception:
        return Response("Unauthorized", 401)
    if not (hmac.compare_digest(u, BASIC_USER) and hmac.compare_digest(p, BASIC_PASS)):
        return Response("Unauthorized", 401)
    return None


@app.get("/full/<source_id>.xml")
def feed_one(source_id: str):
    limit = min(env_int("RSS_LIMIT", 50), 500)
    rows = query_rows(source_id, limit)
    only_full = request.args.get("only_full", "0") == "1"
    body = render_feed(rows, f"公众号 {source_id} · 全文",
                       f"{PUBLIC_BASE}/full/{source_id}.xml", only_full)
    return Response(body, mimetype="application/rss+xml; charset=utf-8")


@app.get("/all.xml")
def feed_all():
    limit = min(env_int("RSS_LIMIT", 100), 500)
    rows = query_rows(None, limit)
    only_full = request.args.get("only_full", "0") == "1"
    body = render_feed(rows, "全部公众号 · 全文聚合",
                       f"{PUBLIC_BASE}/all.xml", only_full)
    return Response(body, mimetype="application/rss+xml; charset=utf-8")


@app.get("/articles.json")
def articles_json():
    """给不想解析 XML 的 Agent：直接拿结构化正文。"""
    limit = min(int(request.args.get("limit", "50")), 500)
    sid = request.args.get("source_id")
    rows = query_rows(sid, limit)
    if request.args.get("only_full", "0") == "1":
        rows = [r for r in rows if r["status"] == "ok"]
    return jsonify([{
        "guid": r["guid"], "source_id": r["source_id"], "source_name": r["source_name"],
        "title": r["title"], "link": r["link"], "pub_date": r["pub_date"],
        "summary": r["summary"], "status": r["status"],
        "content_html": r["content_html"] if r["status"] == "ok" else "",
        "fetched_at": r["fetched_at"], "error": r["error"],
    } for r in rows])


@app.get("/healthz")
def healthz():
    with db() as c:
        counts = dict(c.execute("SELECT status, COUNT(*) FROM articles GROUP BY status").fetchall())
        total = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        last = c.execute("SELECT MAX(fetched_at) FROM articles WHERE status='ok'").fetchone()[0]
    return jsonify({
        "total": total, "by_status": counts,
        "last_success_at": last,
        "poll_interval": POLL_INTERVAL, "fetch_delay": FETCH_DELAY,
        "auto_discover": AUTO_DISCOVER,
    })


@app.post("/retry")
def retry():
    """把失败/被拦的条目重新排进队列，人工确认风控解除后再调用。"""
    with db() as c:
        n = c.execute(
            "UPDATE articles SET status='pending', attempts=0, next_retry=0, error='' "
            "WHERE status IN ('blocked','error')"
        ).rowcount
    return jsonify({"requeued": n})


@app.get("/")
def index():
    with db() as c:
        src = c.execute(
            "SELECT source_id, source_name, COUNT(*) n, "
            "SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) ok "
            "FROM articles GROUP BY source_id ORDER BY source_id"
        ).fetchall()
        counts = dict(c.execute("SELECT status, COUNT(*) FROM articles GROUP BY status").fetchall())
    rows = "".join(
        f"<tr><td>{html.escape(str(r['source_id']))}</td>"
        f"<td>{html.escape(str(r['source_name']))}</td>"
        f"<td>{r['n']}</td><td>{r['ok']}</td>"
        f"<td><a href='/full/{html.escape(str(r['source_id']))}.xml'>全文 RSS</a> "
        f"· <a href='/full/{html.escape(str(r['source_id']))}.xml?only_full=1'>仅全文</a></td></tr>"
        for r in src
    )
    return Response(f"""<!doctype html><meta charset="utf-8">
<title>wechrss 全文中间层</title>
<style>body{{font:15px/1.6 -apple-system,sans-serif;margin:40px;color:#222}}
table{{border-collapse:collapse}}td,th{{padding:6px 14px;border-bottom:1px solid #ddd}}
code{{background:#f4f4f4;padding:2px 5px}}</style>
<h2>全文中间层</h2>
<p>聚合：<a href="/all.xml">/all.xml</a> ·
<a href="/all.xml?only_full=1">仅全文</a> ·
<a href="/articles.json">/articles.json</a> ·
<a href="/healthz">/healthz</a></p>
<p>状态：{html.escape(str(counts))}</p>
<table><tr><th>源</th><th>名称</th><th>条目</th><th>已抓全文</th><th>订阅</th></tr>{rows}</table>
<p>被风控拦下的条目不会污染 RSS；确认解除后可
<code>curl -X POST {html.escape(PUBLIC_BASE)}/retry</code> 重新排队。</p>
""", mimetype="text/html; charset=utf-8")


if __name__ == "__main__":
    init_db()
    log.info("启动: upstream=%s auto_discover=%s poll=%ss delay=%ss db=%s",
             UPSTREAM_BASE, AUTO_DISCOVER, POLL_INTERVAL, FETCH_DELAY, DB_PATH)
    threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
