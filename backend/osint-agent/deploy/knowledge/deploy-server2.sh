#!/usr/bin/env bash
# Deploy Qwen3-Embedding-0.6B CPU service on server 2 (Task2 Stage F).
set -euo pipefail

PW="${SUDO_PW:?set SUDO_PW}"
ASKPASS="$(mktemp)"
trap 'rm -f "$ASKPASS"' EXIT
printf '#!/bin/sh\necho "%s"\n' "$PW" >"$ASKPASS"
chmod 700 "$ASKPASS"
export SUDO_ASKPASS="$ASKPASS"
sudo() { command sudo -A -p '' "$@"; }

BASE=/opt/macromind-knowledge
SRV=/srv/macromind-knowledge

echo "=== dirs ==="
sudo mkdir -p "$BASE/services/embedding" "$SRV/models" "$SRV/work" "$SRV/backups"
sudo chown -R "$USER:$USER" "$BASE" "$SRV"

echo "=== python venv ==="
if [[ ! -x "$BASE/venv/bin/python" ]]; then
  python3 -m venv "$BASE/venv"
fi
"$BASE/venv/bin/pip" install -q --upgrade pip
# CPU torch from official CPU index (any available 2.x)
"$BASE/venv/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu
"$BASE/venv/bin/pip" install -q 'sentence-transformers>=3.0,<4' 'fastapi>=0.109' 'uvicorn[standard]>=0.27' 'pydantic>=2.5'
"$BASE/venv/bin/python" -c "import torch,sentence_transformers,fastapi; print('torch',torch.__version__,'st',sentence_transformers.__version__)"

echo "=== service code ==="
SRC="${SRC_DIR:-$HOME/macromind-knowledge-deploy/services/embedding}"
cp -f "$SRC/embedding_service.py" "$BASE/services/embedding/"
ls -la "$BASE/services/embedding"

echo "=== model (HF cache or local copy) ==="
export HF_HOME="$SRV/models/hf"
export TRANSFORMERS_CACHE="$SRV/models/hf"
export EMBED_MODEL_ID=Qwen/Qwen3-Embedding-0.6B
export EMBED_REVISION=main
export EMBED_DIM=1024
export EMBED_MAX_TOKENS=1024
export EMBED_BATCH_SIZE=1
export EMBED_THREADS=4

# warm download / load once so startup is fast
"$BASE/venv/bin/python" - <<'PY'
import os
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device="cpu")
v = model.encode(["привет"], normalize_embeddings=True)
print("dim", len(v[0]), "ok")
PY

echo "=== start service ==="
# kill previous if any
pkill -f "uvicorn embedding_service:app" 2>/dev/null || true
sleep 1
cd "$BASE/services/embedding"
nohup "$BASE/venv/bin/uvicorn" embedding_service:app \
  --host 10.77.0.2 --port 8091 \
  >"$SRV/work/embedding.log" 2>&1 &
echo $! >"$SRV/work/embedding.pid"
sleep 8
curl -sS -m 5 "http://127.0.0.1:8091/health/ready" || true
echo
curl -sS -m 5 "http://127.0.0.1:8091/health/live" || true
echo
echo "OK server2 embedding on 10.77.0.2:8091"
