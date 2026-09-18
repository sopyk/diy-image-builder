#!/bin/bash
# mem0-api 生产启动入口（diy-image-builder 自定义，幂等）。
#
# 顺序：
#   1. patch-main.sh   把上游 main.py 注入 LLM/embedder/vector_store 定制（幂等）
#   2. wait-for-db     等 postgres 可连（compose 有 healthcheck，这里再加一道短重试）
#   3. ensure-vector-dims
#        配置的 embedding 维度（MEM0_EMBEDDER_DIMS，默认 1536）必须与已存在的
#        memories 表向量列维度一致。上游默认 1536，换 bge-m3(1024) 时：
#          - 表不存在 → mem0 会按配置自动建表，无需处理
#          - 表存在且为空 → 自动 ALTER 列维度 + 重建 HNSW 索引
#          - 表存在且有数据且维度不符 → 拒绝启动（静默降维会毁数据，需人工决策）
#   4. alembic upgrade head
#        上游生产镜像 CMD 漏了迁移（dev compose 才有），首次启动需要它建
#        users/api_keys/request_logs 等表；之后每周 Actions 构建带入的新迁移
#        也会在容器重启时自动应用。
#   5. uvicorn
set -e

APP=/app
cd "$APP"

echo "[entrypoint] 1/5 applying main.py patch"
/usr/local/bin/patch-main.sh

WANTED_DIMS="${MEM0_EMBEDDER_DIMS:-1536}"

echo "[entrypoint] 2/5 waiting for postgres"
python3 - "$WANTED_DIMS" <<'PYEOF'
import os, sys, time

import psycopg

wanted = int(sys.argv[1])
dsn = (
    f"host={os.environ.get('POSTGRES_HOST','postgres')} "
    f"port={os.environ.get('POSTGRES_PORT','5432')} "
    f"dbname={os.environ.get('POSTGRES_DB','postgres')} "
    f"user={os.environ.get('POSTGRES_USER','postgres')} "
    f"password={os.environ['POSTGRES_PASSWORD']} connect_timeout=3"
)

last = None
for attempt in range(30):
    try:
        conn = psycopg.connect(dsn, autocommit=True)
        break
    except Exception as e:  # noqa: BLE001
        last = e
        time.sleep(2)
else:
    print(f"[entrypoint] postgres unreachable after 60s: {last}", file=sys.stderr)
    sys.exit(1)

coll = os.environ.get("POSTGRES_COLLECTION_NAME", "memories")

with conn.cursor() as cur:
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name=%s", (coll,)
    )
    exists = cur.fetchone() is not None

    if not exists:
        print(f"[entrypoint] 3/5 table '{coll}' not present; mem0 will create it "
              f"with {wanted} dims on first use")
        conn.close()
        sys.exit(0)

    cur.execute(
        "SELECT atttypmod FROM pg_attribute "
        "WHERE attrelid=%s::regclass AND attname='vector'",
        (f"public.{coll}",),
    )
    row = cur.fetchone()
    if not row:
        # 表存在但还没有 vector 列（异常状态），交给应用建列
        print(f"[entrypoint] 3/5 '{coll}.vector' missing; leaving to application")
        conn.close()
        sys.exit(0)

    # pg vector 类型的 atttypmod 即维度
    current = int(row[0])
    cur.execute(f"SELECT count(*) FROM public.{coll}")
    n = cur.fetchone()[0]

    if current == wanted:
        print(f"[entrypoint] 3/5 vector dims already {wanted} (rows={n})")
    elif n == 0:
        print(f"[entrypoint] 3/5 empty table: altering vector {current} -> {wanted}")
        cur.execute(f"DROP INDEX IF EXISTS {coll}_hnsw_idx")
        cur.execute(
            f"ALTER TABLE public.{coll} ALTER COLUMN vector TYPE vector({wanted})"
        )
        cur.execute(
            f"CREATE INDEX {coll}_hnsw_idx ON public.{coll} "
            f"USING hnsw (vector vector_cosine_ops)"
        )
        print(f"[entrypoint] vector column rebuilt at {wanted} dims + HNSW index")
    else:
        print(
            f"[entrypoint] FATAL: '{coll}' has {n} rows at {current} dims but "
            f"MEM0_EMBEDDER_DIMS={wanted}. Refusing to start: dimensional change "
            f"with existing data requires explicit re-embedding/migration.",
            file=sys.stderr,
        )
        conn.close()
        sys.exit(2)

conn.close()
PYEOF

echo "[entrypoint] 4/5 alembic upgrade head"
alembic upgrade head

echo "[entrypoint] 5/5 starting uvicorn"
exec uvicorn main:app --host 0.0.0.0 --port 8000
