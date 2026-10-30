#!/usr/bin/env bash
# Restore knowledge backup into a SEPARATE test database (Task2 §15, R35).
# Never restore over the live database in this script.
set -euo pipefail

SRC="${1:?usage: restore.sh /path/to/backup [new_db_name]}"
NEW_DB="${2:-knowledge_restore_test}"
CONTAINER="${KNOWLEDGE_PG_CONTAINER:-macromind-knowledge-pg}"
USER="${KNOWLEDGE_PG_USER:-knowledge}"
RESTORE_ROOT="${KNOWLEDGE_RESTORE_OBJECTS:-/srv/macromind-knowledge/restore-test}"
if ! mkdir -p "$RESTORE_ROOT" 2>/dev/null; then
  RESTORE_ROOT="/tmp/macromind-knowledge-restore-test"
  mkdir -p "$RESTORE_ROOT"
  echo "NOTE: fallback restore root $RESTORE_ROOT"
fi

[[ -f "$SRC/knowledge.dump" ]] || { echo "missing $SRC/knowledge.dump"; exit 1; }
[[ -f "$SRC/SHA256SUMS" ]] && (cd "$SRC" && sha256sum -c SHA256SUMS)

# verify object manifest
if [[ -f "$SRC/objects_manifest.json" ]]; then
  python3 - <<PY
import hashlib, json, os, sys
src = "${SRC}/objects"
man = json.load(open("${SRC}/objects_manifest.json"))
bad = 0
for e in man:
    p = os.path.join(src, e["file"])
    if not os.path.isfile(p):
        print("MISSING", e["file"]); bad += 1; continue
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    if h != e["sha256"]:
        print("BAD HASH", e["file"]); bad += 1
print(f"checked {len(man)} objects, bad={bad}")
sys.exit(1 if bad else 0)
PY
fi

# restore objects to isolated root
mkdir -p "$RESTORE_ROOT"
if [[ -d "$SRC/objects" ]]; then
  cp -a "$SRC/objects/." "$RESTORE_ROOT/"
fi

# restore dump into new database
docker exec "$CONTAINER" psql -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS ${NEW_DB}" >/dev/null
docker exec "$CONTAINER" psql -U "$USER" -d postgres -c "CREATE DATABASE ${NEW_DB}" >/dev/null
docker cp "$SRC/knowledge.dump" "$CONTAINER":/tmp/restore.dump
docker exec "$CONTAINER" pg_restore -U "$USER" -d "$NEW_DB" --no-owner /tmp/restore.dump
docker exec "$CONTAINER" rm -f /tmp/restore.dump

# smoke checks (R35): tables exist, one report/evidence readable
docker exec "$CONTAINER" psql -U "$USER" -d "$NEW_DB" -Atc \
  "select count(*) from pg_tables where schemaname='public'"
docker exec "$CONTAINER" psql -U "$USER" -d "$NEW_DB" -Atc \
  "select 'docs='||count(*) from documents"
docker exec "$CONTAINER" psql -U "$USER" -d "$NEW_DB" -Atc \
  "select 'reports='||count(*) from report_versions"

echo "OK restored to database=${NEW_DB} objects=${RESTORE_ROOT}"
echo "NOTE: live database untouched. Drop ${NEW_DB} when done."
