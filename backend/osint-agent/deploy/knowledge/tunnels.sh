#!/usr/bin/env bash
# SSH tunnels from work machine to knowledge services on 10.77.0.* (via server1).
# Workstation is on Wi-Fi and cannot reach wired 10.77.0.0/30 directly.
#
# Usage:
#   bash deploy/knowledge/tunnels.sh start
#   bash deploy/knowledge/tunnels.sh stop
#   bash deploy/knowledge/tunnels.sh status
#
# After start:
#   KNOWLEDGE_DATABASE_URL=postgresql://knowledge:***@127.0.0.1:15432/knowledge
#   EMBEDDING_BASE_URL=http://127.0.0.1:18091
set -euo pipefail

PIDFILE="${PIDFILE:-/tmp/macromind-knowledge-tunnels.pid}"
LOCAL_PG_PORT="${LOCAL_PG_PORT:-15432}"
LOCAL_EMB_PORT="${LOCAL_EMB_PORT:-18091}"
JUMP="${JUMP:-server1}"  # ~/.ssh/config
REMOTE_PG="10.77.0.1:5432"
REMOTE_EMB="10.77.0.2:8091"

start() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "already running pid=$(cat "$PIDFILE")"
    return 0
  fi
  ssh -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -L "${LOCAL_PG_PORT}:${REMOTE_PG}" \
    -L "${LOCAL_EMB_PORT}:${REMOTE_EMB}" \
    -N "$JUMP" &
  echo $! >"$PIDFILE"
  sleep 2
  echo "tunnels up pid=$(cat "$PIDFILE")"
  echo "  PG  127.0.0.1:${LOCAL_PG_PORT} -> ${REMOTE_PG}"
  echo "  EMB 127.0.0.1:${LOCAL_EMB_PORT} -> ${REMOTE_EMB}"
}

stop() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "stopped"
  else
    echo "not running"
  fi
}

status() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "running pid=$(cat "$PIDFILE")"
  else
    echo "stopped"
  fi
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
