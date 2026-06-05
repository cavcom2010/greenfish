#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$ROOT/.production/run"
PID_FILE="$RUN_DIR/gunicorn.pid"
PRODUCTION_SERVICE_NAME="${PRODUCTION_SERVICE_NAME:-greenfish-gunicorn.service}"
STOP_SYSTEMD=0

print_usage() {
  cat <<'EOF'
Usage: ./deploy/production/stop.sh [--systemd] [--help]

Default behavior:
  Stop only the production debug Gunicorn process started by
  ./deploy/production/start.sh --daemon.

Options:
  --systemd  Stop the live greenfish-gunicorn systemd service and socket.
  --help     Show this help text.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --systemd)
      STOP_SYSTEMD=1
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "$STOP_SYSTEMD" == "1" ]]; then
  echo "Stopping live ${PRODUCTION_SERVICE_NAME} and its socket..."
  sudo systemctl stop "$PRODUCTION_SERVICE_NAME"
  socket_name="${PRODUCTION_SERVICE_NAME%.service}.socket"
  sudo systemctl stop "$socket_name" 2>/dev/null || true
  echo "Live GreenFish service stopped."
  exit 0
fi

if [[ ! -f "$PID_FILE" ]]; then
  echo "No production debug Gunicorn PID file found at $PID_FILE."
  exit 0
fi

pid="$(tr -dc '0-9' < "$PID_FILE")"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE"
  echo "Removed empty PID file."
  exit 0
fi

if kill -0 "$pid" 2>/dev/null; then
  echo "Stopping production debug Gunicorn pid ${pid}..."
  kill -TERM "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
  echo "Production debug Gunicorn stopped."
else
  echo "PID ${pid} is not running."
fi

rm -f "$PID_FILE"
