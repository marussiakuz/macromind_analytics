#!/usr/bin/env bash
# Backup knowledge PostgreSQL + object store (Task2 §15).
# Logical dump + immutable object copy + manifest with hashes.
set -euo pipefail

ROOT="${KNOWLEDGE_OBJECTS_ROOT:-/srv/macromind-knowledge/objects}"
OUT="${1:-/srv/macromind-knowledge/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
CONTAINER="${KNOWLEDGE_PG_CONTAINER:-macromind-knowledge-pg}"
DB="${KNOWLEDGE_PG_DB:-knowledge}"
USER="${KNOWLEDGE_PG_USER:-knowledge}"

mkdir -p "$OUT/objects"
echo "→ $OUT"

# 1) consistent logical dump
docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" -Fc -f /tmp/knowledge.dump
docker cp "$CONTAINER":/tmp/knowledge.dump "$OUT/knowledge.dump"
docker exec "$CONTAINER" rm -f /tmp/knowledge.dump

# 2) extension / role versions (no secrets)
docker exec "$CONTAINER" psql -U "$USER" -d "$DB" -Atc \
  "select extname||' '||extversion from pg_extension order by 1" > "$OUT/extensions.txt"

# 3) copy objects + verify hashes
if [[ -d "$ROOT" ]]; then
  # hardlink-free copy; files are immutable
  (cd "$ROOT" && find . -type f ! -name '.tmp-*' -print0) | while IFS= read -r -d '' f; do
    mkdir -p "$OUT/objects/$(dirname "$f")"
    cp -n "$ROOT/$f" "$OUT/objects/$f" || true
    exp="$(basename "$f")"
    got="$(sha256sum "$OUT/objects/$f" | awk '{print $1}')"
    if [[ "$exp" != "$got" && "$exp" != .* ]]; then
      # content-addressed name should equal hash; warn if not
      echo "WARN hash mismatch $f exp=$exp got=$got" >> "$OUT/hash_warnings.txt"
    fi
  done
  python3 - <<PY
import hashlib, json, os
root = "${OUT}/objects"
manifest = []
for dirpath, _, files in os.walk(root):
    for name in files:
        if name.startswith(".tmp-"):
            continue
        p = os.path.join(dirpath, name)
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        manifest.append({"file": os.path.relpath(p, root), "sha256": h.hexdigest(), "size": os.path.getsize(p)})
with open("${OUT}/objects_manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(f"manifest objects: {len(manifest)}")
PY
fi

# 4) checksums of archive
( cd "$OUT" && sha256sum knowledge.dump extensions.txt objects_manifest.json > SHA256SUMS )
echo "OK backup at $OUT"
