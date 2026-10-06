#!/bin/bash
# Local PostgreSQL control:  bash scripts/db.sh init|start|stop|status|psql|reset
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
PGDATA_DIR="$(pwd)/.pgdata"
PORT="${PGPORT:-55432}"; DBUSER="${PGUSER:-aopx}"; PASS="${PGPASSWORD:-aopx}"; DB="${PGDATABASE:-agentops}"
SOCK="/tmp/aopx-pg-$(id -u)"

start() {
  mkdir -p "$SOCK"
  # data dir may come from a session on another machine: clear a stale lock from a different host
  if [ -f "$PGDATA_DIR/postmaster.pid" ] && [ "$(cat "$PGDATA_DIR/.host" 2>/dev/null)" != "$(hostname)" ]; then
    rm -f "$PGDATA_DIR/postmaster.pid"
  fi
  if pg_ctl -D "$PGDATA_DIR" status >/dev/null 2>&1; then echo "postgres already running on :$PORT"; return; fi
  hostname > "$PGDATA_DIR/.host"
  pg_ctl -D "$PGDATA_DIR" -l "$PGDATA_DIR/server.log" -o "-p $PORT -h 127.0.0.1 -k $SOCK" -w start >/dev/null
  echo "postgres started on 127.0.0.1:$PORT"
}

case "${1:-status}" in
  init)
    if [ ! -d "$PGDATA_DIR" ]; then
      pw=$(mktemp); echo "$PASS" > "$pw"
      initdb -D "$PGDATA_DIR" -U "$DBUSER" --pwfile="$pw" -A scram-sha-256 >/dev/null
      rm -f "$pw"
    fi
    start
    PGPASSWORD="$PASS" createdb -h 127.0.0.1 -p "$PORT" -U "$DBUSER" "$DB" 2>/dev/null || true
    echo "database '$DB' ready" ;;
  start)  start ;;
  stop)   pg_ctl -D "$PGDATA_DIR" -m fast stop ;;
  status) pg_ctl -D "$PGDATA_DIR" status || true ;;
  psql)   PGPASSWORD="$PASS" psql -h 127.0.0.1 -p "$PORT" -U "$DBUSER" "$DB" ;;
  reset)  PGPASSWORD="$PASS" dropdb -h 127.0.0.1 -p "$PORT" -U "$DBUSER" --if-exists "$DB" && \
          PGPASSWORD="$PASS" createdb -h 127.0.0.1 -p "$PORT" -U "$DBUSER" "$DB" && echo "database reset" ;;
  *) echo "usage: $0 init|start|stop|status|psql|reset"; exit 1 ;;
esac
