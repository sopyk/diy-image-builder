#!/bin/bash
# 对上游 server/main.py 做最小注入：让 LLM 和 embedder 的 openai base_url
# 可以分别用环境变量覆盖（上游只支持共用一个 OPENAI_BASE_URL，无法 LLM 走云端、
# embedder 走本地 Ollama）。
#
# 新增环境变量（都可选；不设则行为与官方一致）：
#   MEM0_LLM_BASE_URL       LLM 的 OpenAI 兼容端点（如火山方舟 /v3）
#   MEM0_EMBEDDER_BASE_URL  embedder 的 OpenAI 兼容端点（如本地 Ollama /v1）
set -e
F=/app/main.py

# 幂等：已打过补丁则跳过
if grep -q "MEM0_LLM_BASE_URL" "$F"; then
  echo "[patch] main.py already patched"
  exit 0
fi

python3 - <<'PYEOF'
import re
p = "/app/main.py"
s = open(p).read()

# 在 DEFAULT_CONFIG 定义之后、initialize_state 之前注入 base_url
anchor = "set_session_factory(SessionLocal)"
inject = '''# --- diy-image-builder patch: per-component OpenAI base_url ---
import os as _os
_llm_base = _os.environ.get("MEM0_LLM_BASE_URL")
_emb_base = _os.environ.get("MEM0_EMBEDDER_BASE_URL")
if _llm_base:
    DEFAULT_CONFIG["llm"].setdefault("config", {})["openai_base_url"] = _llm_base
if _emb_base:
    DEFAULT_CONFIG["embedder"].setdefault("config", {})["openai_base_url"] = _emb_base
# --- end patch ---

set_session_factory(SessionLocal)'''

if anchor not in s:
    raise SystemExit("anchor not found in main.py; upstream layout changed - patch aborted")
s = s.replace(anchor, inject, 1)
open(p, "w").write(s)
print("[patch] injected per-component base_url support")
PYEOF
