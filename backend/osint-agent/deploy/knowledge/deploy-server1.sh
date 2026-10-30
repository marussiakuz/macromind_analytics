#!/usr/bin/env bash
# Deploy knowledge PostgreSQL on server 1 (Task2 Stage F).
# Does NOT touch radar containers. Pinned image. Idempotent.
set -euo pipefail

PW="${SUDO_PW:?set SUDO_PW}"
ASKPASS="$(mktemp)"
trap 'rm -f "$ASKPASS"' EXIT
printf '#!/bin/sh\necho "%s"\n' "$PW" >"$ASKPASS"
chmod 700 "$ASKPASS"
export SUDO_ASKPASS="$ASKPASS"
sudo() { command sudo -A -p '' "$@"; }

echo "=== mkdir ==="
sudo mkdir -p /opt/macromind-knowledge /srv/macromind-knowledge/{objects,backups,restore-test}
sudo chown -R "$USER:$USER" /opt/macromind-knowledge /srv/macromind-knowledge

echo "=== image ==="
sudo docker pull pgvector/pgvector:pg16

echo "=== container ==="
if sudo docker ps -a --format '{{.Names}}' | grep -q '^macromind-knowledge-pg$'; then
  echo "container exists — starting"
  sudo docker start macromind-knowledge-pg
else
  sudo docker run -d --name macromind-knowledge-pg \
    --restart unless-stopped \
    -e POSTGRES_DB=knowledge \
    -e POSTGRES_USER=knowledge \
    -e POSTGRES_PASSWORD="${KNOWLEDGE_PG_PASSWORD:-knowledge_local_dev}" \
    -p 10.77.0.1:5432:5432 \
    -v macromind_knowledge_pg:/var/lib/postgresql/data \
    --memory=3g \
    pgvector/pgvector:pg16 \
    postgres -c shared_buffers=512MB -c work_mem=8MB -c max_connections=40
fi

sleep 3
echo "=== health ==="
sudo docker exec macromind-knowledge-pg pg_isready -U knowledge -d knowledge

echo "=== migrations ==="
MIG_DIR="${MIG_DIR:-$HOME/macromind-knowledge-deploy/migrations}"
for f in "$MIG_DIR"/000*.sql; do
  echo "apply $f"
  # password must NOT be on this stdin — only the SQL file
  sudo docker exec -i macromind-knowledge-pg psql -U knowledge -d knowledge -v ON_ERROR_STOP=1 <"$f"
done

echo "=== extensions / tables ==="
sudo docker exec macromind-knowledge-pg psql -U knowledge -d knowledge -Atc \
  "select extname||' '||extversion from pg_extension order by 1"
sudo docker exec macromind-knowledge-pg psql -U knowledge -d knowledge -Atc \
  "select tablename from pg_tables where schemaname='public' order by 1"

echo "OK server1 knowledge-pg on 10.77.0.1:5432"
