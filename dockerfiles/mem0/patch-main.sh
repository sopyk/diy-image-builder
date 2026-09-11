#!/bin/bash
# 对上游 server/main.py 做最小注入（diy-image-builder 维护，幂等）。
#
# 背景：自托管 server 的 DEFAULT_CONFIG 只支持 LLM/embedder 共用一个
# OPENAI_API_KEY + OPENAI_BASE_URL，无法让 LLM 与 embedder 指向不同端点。
# 官方文档给出的扩展方式就是改 server/main.py 后重建镜像。这里用环境变量
# 注入，避免改 provider 白名单、不加新依赖（Ollama/方舟都走 OpenAI 兼容 /v1）。
#
# 新增环境变量（均可选；不设则与官方行为一致）：
#   MEM0_LLM_BASE_URL        LLM 的 OpenAI 兼容端点（火山方舟 .../v3）
#   MEM0_EMBEDDER_BASE_URL   embedder 的 OpenAI 兼容端点（Ollama .../v1）
#   MEM0_EMBEDDER_DIMS       embedder 向量维度（bge-m3=1024；默认 OpenAI 1536）
set -e
F=/app/main.py

if grep -q "MEM0_LLM_BASE_URL" "$F"; then
  echo "[patch] main.py already patched"
  exit 0
fi

python3 - <<'PYEOF'
p = "/app/main.py"
s = open(p).read()

anchor = "set_session_factory(SessionLocal)"
inject = '''# --- diy-image-builder patch: per-component base_url + embedder dims ---
import os as _os
_llm_base = _os.environ.get("MEM0_LLM_BASE_URL")
_emb_base = _os.environ.get("MEM0_EMBEDDER_BASE_URL")
_emb_dims = _os.environ.get("MEM0_EMBEDDER_DIMS")
if _llm_base:
    DEFAULT_CONFIG["llm"].setdefault("config", {})["openai_base_url"] = _llm_base
if _emb_base:
    DEFAULT_CONFIG["embedder"].setdefault("config", {})["openai_base_url"] = _emb_base
if _emb_dims:
    DEFAULT_CONFIG["embedder"].setdefault("config", {})["embedding_dims"] = int(_emb_dims)
# --- end patch ---

set_session_factory(SessionLocal)'''

if anchor not in s:
    raise SystemExit("anchor not found in main.py; upstream layout changed - patch aborted")
s = s.replace(anchor, inject, 1)
open(p, "w").write(s)
print("[patch] injected per-component base_url + embedder dims support")
PYEOF
