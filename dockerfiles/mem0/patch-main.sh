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
#
# v2（2026-09）：MEM0_EMBEDDER_DIMS 必须同时注入 vector_store 的
# embedding_model_dims。只设 embedder.embedding_dims 会让「产出向量」与
# 「pgvector 建表列维度」错配（embedder 产 1024、表仍是默认 1536），
# 表现为写入静默失败、表永远是空的。
set -e
F=/app/main.py
TAG="diy-image-builder patch"

# v1 旧版补丁只注入了 embedder.embedding_dims，检测到 v1 标记时整段替换为 v2。
if grep -q "$TAG v2" "$F"; then
  echo "[patch] main.py already patched (v2)"
  exit 0
fi

python3 - <<'PYEOF'
p = "/app/main.py"
s = open(p).read()

# 移除 v1 注入块（如果存在），保证从旧镜像源码升级时也能幂等重打。
v1_start = "# --- diy-image-builder patch: per-component base_url + embedder dims ---"
v1_end_marker = "set_session_factory(SessionLocal)"
if v1_start in s:
    i = s.index(v1_start)
    j = s.index(v1_end_marker, i)
    s = s[:i] + s[j:]
    print("[patch] removed v1 injection block")

anchor = "set_session_factory(SessionLocal)"
inject = '''# --- diy-image-builder patch v2: per-component base_url + embedder/vector dims ---
import os as _os
_llm_base = _os.environ.get("MEM0_LLM_BASE_URL")
_emb_base = _os.environ.get("MEM0_EMBEDDER_BASE_URL")
_emb_dims = _os.environ.get("MEM0_EMBEDDER_DIMS")
if _llm_base:
    DEFAULT_CONFIG["llm"].setdefault("config", {})["openai_base_url"] = _llm_base
if _emb_base:
    DEFAULT_CONFIG["embedder"].setdefault("config", {})["openai_base_url"] = _emb_base
if _emb_dims:
    _dims = int(_emb_dims)
    # embedder 产出维度
    DEFAULT_CONFIG["embedder"].setdefault("config", {})["embedding_dims"] = _dims
    # pgvector 建表/列维度：漏了它会导致表按默认 1536 建，写入维度错配
    DEFAULT_CONFIG["vector_store"].setdefault("config", {})["embedding_model_dims"] = _dims
# --- end diy-image-builder patch ---

set_session_factory(SessionLocal)'''

if anchor not in s:
    raise SystemExit("anchor not found in main.py; upstream layout changed - patch aborted")
s = s.replace(anchor, inject, 1)
open(p, "w").write(s)
print("[patch] injected v2 (base_url + embedder/vector_store dims)")
PYEOF
