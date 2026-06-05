#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON_BIN="$ROOT/venv/bin/python"
PIP_BIN="$ROOT/venv/bin/pip"
GUNICORN_BIN="$ROOT/venv/bin/gunicorn"
RUN_DIR="$ROOT/.production/run"
LOG_DIR="$ROOT/.production/logs"
PID_FILE="$RUN_DIR/gunicorn.pid"

PRODUCTION_SERVICE_NAME="${PRODUCTION_SERVICE_NAME:-greenfish-gunicorn.service}"
PRODUCTION_HEALTH_URL="${PRODUCTION_HEALTH_URL:-https://greenfish.calvinmazhindu.dev/health/}"
PRODUCTION_BIND="${PRODUCTION_BIND:-127.0.0.1:${PRODUCTION_DEBUG_PORT:-8126}}"
PRODUCTION_WORKERS="${PRODUCTION_WORKERS:-2}"
PRODUCTION_TIMEOUT="${PRODUCTION_TIMEOUT:-60}"
PRODUCTION_GRACEFUL_TIMEOUT="${PRODUCTION_GRACEFUL_TIMEOUT:-15}"
PRODUCTION_KEEP_ALIVE="${PRODUCTION_KEEP_ALIVE:-5}"

RUN_FOREGROUND=1
RUN_PULL="${PRODUCTION_PULL:-1}"
RUN_INSTALL="${PRODUCTION_INSTALL:-1}"
RUN_MIGRATE="${PRODUCTION_MIGRATE:-1}"
RUN_COLLECTSTATIC="${PRODUCTION_COLLECTSTATIC:-1}"
RUN_RELOAD_LIVE=0
RUN_SYSTEMD=0

print_usage() {
  cat <<'EOF'
Usage: ./deploy/production/start.sh [options]

Default behavior:
  - Pull origin/main with --ff-only.
  - Install requirements.txt.
  - Run Django checks, migration dry-run, migrations, and collectstatic.
  - Start Gunicorn in the foreground on 127.0.0.1:8126 for live error visibility.

Options:
  --foreground       Stream Gunicorn logs in this terminal (default).
  --daemon           Start the debug Gunicorn process in the background.
  --bind VALUE       Override debug bind address. Example: 127.0.0.1:8126.
  --no-pull          Skip git fetch/pull.
  --no-install       Skip pip install.
  --no-migrate       Skip migrations.
  --no-static        Skip collectstatic.
  --reload-live      After release checks, HUP the live Gunicorn master and exit.
  --systemd          Restart the systemd service and follow journal logs.
  --help             Show this help text.

Environment:
  PRODUCTION_BIND=127.0.0.1:8126
  PRODUCTION_SERVICE_NAME=greenfish-gunicorn.service
  PRODUCTION_HEALTH_URL=https://greenfish.calvinmazhindu.dev/health/

Notes:
  Foreground debug mode intentionally binds to a separate localhost port so the
  live website keeps serving while startup errors are inspected.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground)
      RUN_FOREGROUND=1
      ;;
    --daemon)
      RUN_FOREGROUND=0
      ;;
    --bind)
      shift
      [[ $# -gt 0 ]] || { echo "--bind requires a value." >&2; exit 1; }
      PRODUCTION_BIND="$1"
      ;;
    --no-pull)
      RUN_PULL=0
      ;;
    --no-install)
      RUN_INSTALL=0
      ;;
    --no-migrate)
      RUN_MIGRATE=0
      ;;
    --no-static)
      RUN_COLLECTSTATIC=0
      ;;
    --reload-live)
      RUN_RELOAD_LIVE=1
      ;;
    --systemd)
      RUN_SYSTEMD=1
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

if [[ ! -x "$PYTHON_BIN" ]] || [[ ! -x "$PIP_BIN" ]] || [[ ! -x "$GUNICORN_BIN" ]]; then
  echo "Missing venv binaries at $ROOT/venv. Create/install the virtualenv first." >&2
  exit 1
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export PYTHONUNBUFFERED=1

run_manage() {
  echo "Running python manage.py $*..."
  "$PYTHON_BIN" manage.py "$@"
}

git_release_update() {
  if [[ "$RUN_PULL" != "1" ]]; then
    return
  fi
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Refusing to pull because the production worktree has local changes." >&2
    git status --short >&2
    exit 1
  fi
  echo "Fetching and fast-forwarding origin/main..."
  git fetch origin main --prune
  git pull --ff-only origin main
}

install_requirements() {
  if [[ "$RUN_INSTALL" == "1" ]]; then
    echo "Installing requirements.txt..."
    "$PIP_BIN" install -r requirements.txt
  fi
}

preflight_django() {
  run_manage check
  run_manage makemigrations --check --dry-run
  if [[ "$RUN_MIGRATE" == "1" ]]; then
    run_manage migrate --noinput
  else
    run_manage migrate --check --noinput
  fi
  if [[ "$RUN_COLLECTSTATIC" == "1" ]]; then
    run_manage collectstatic --noinput
  fi
}

candidate_gunicorn_masters() {
  ps -eo pid=,ppid=,user=,cmd= \
    | awk -v root="$ROOT" -v user="$(id -un)" '
      $3 == user && index($0, root "/venv/bin/gunicorn") && index($0, "config.wsgi:application") {
        print $1, $2
      }
    '
}

live_master_pid() {
  local rows=""
  local pid=""
  local ppid=""
  rows="$(candidate_gunicorn_masters || true)"
  [[ -n "$rows" ]] || return 1

  while read -r pid ppid; do
    [[ -z "$pid" ]] && continue
    if ! awk -v ppid="$ppid" '$1 == ppid { found=1 } END { exit found ? 0 : 1 }' <<< "$rows"; then
      printf '%s\n' "$pid"
      return 0
    fi
  done <<< "$rows"

  return 1
}

reload_live_gunicorn() {
  local master_pid=""
  if ! master_pid="$(live_master_pid)"; then
    echo "Could not find live GreenFish Gunicorn master process to reload." >&2
    exit 1
  fi
  echo "Reloading live Gunicorn master pid ${master_pid} with HUP..."
  kill -HUP "$master_pid"
  sleep 2
  if command -v curl >/dev/null 2>&1; then
    echo "Checking live health endpoint..."
    curl -fsS --max-time 10 "$PRODUCTION_HEALTH_URL"
    echo
  fi
}

restart_systemd() {
  echo "Restarting ${PRODUCTION_SERVICE_NAME} with systemd..."
  sudo systemctl restart "$PRODUCTION_SERVICE_NAME"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 10 "$PRODUCTION_HEALTH_URL"
    echo
  fi
  echo "Following journal logs. Press Ctrl+C to stop viewing logs."
  sudo journalctl -fu "$PRODUCTION_SERVICE_NAME"
}

stop_debug_pid() {
  if [[ ! -f "$PID_FILE" ]]; then
    return
  fi
  local pid=""
  pid="$(tr -dc '0-9' < "$PID_FILE")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "Stopping existing production debug Gunicorn pid ${pid}..."
    kill -TERM "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
}

start_debug_gunicorn() {
  stop_debug_pid
  echo "Starting production debug Gunicorn on ${PRODUCTION_BIND}."
  echo "This foreground/debug process is separate from the live systemd socket service."

  local args=(
    --bind "$PRODUCTION_BIND"
    --workers "$PRODUCTION_WORKERS"
    --timeout "$PRODUCTION_TIMEOUT"
    --graceful-timeout "$PRODUCTION_GRACEFUL_TIMEOUT"
    --keep-alive "$PRODUCTION_KEEP_ALIVE"
    --access-logfile -
    --error-logfile -
    --capture-output
    config.wsgi:application
  )

  if [[ "$RUN_FOREGROUND" == "1" ]]; then
    exec "$GUNICORN_BIN" "${args[@]}"
  fi

  "$GUNICORN_BIN" \
    "${args[@]}" \
    --daemon \
    --pid "$PID_FILE" \
    --access-logfile "$LOG_DIR/gunicorn-access.log" \
    --error-logfile "$LOG_DIR/gunicorn-error.log"
  local pid=""
  for _ in {1..40}; do
    if [[ -f "$PID_FILE" ]]; then
      pid="$(tr -dc '0-9' < "$PID_FILE")"
      if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        break
      fi
    fi
    sleep 0.25
  done
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    echo "Gunicorn did not create a running PID. Recent error log:" >&2
    tail -80 "$LOG_DIR/gunicorn-error.log" >&2 || true
    exit 1
  fi
  echo "Production debug Gunicorn started in daemon mode. PID: ${pid}"
  echo "Logs: $LOG_DIR/gunicorn-error.log"
}

git_release_update
install_requirements
preflight_django

if [[ "$RUN_SYSTEMD" == "1" ]]; then
  restart_systemd
elif [[ "$RUN_RELOAD_LIVE" == "1" ]]; then
  reload_live_gunicorn
else
  start_debug_gunicorn
fi
