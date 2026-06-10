#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-$ROOT/venv/bin/python}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
DOMAIN="${DOMAIN:-greenfish.calvinmazhindu.dev}"
BASE_URL="${BASE_URL:-https://$DOMAIN}"

GUNICORN_SERVICE="${GUNICORN_SERVICE:-greenfish-gunicorn.service}"
NGINX_SERVICE_NAME="${NGINX_SERVICE_NAME:-nginx}"
FOLLOW=0
COLLECTSTATIC=1
SKIP_BACKUP=0
RELOAD_NGINX=1
RUN_COMPRESS="${RUN_COMPRESS:-0}"

print_usage() {
  cat <<'EOF'
Usage: ./deploy/production/restart.sh [options]

Runs production Django preflight checks, applies migrations when needed,
collects static files, restarts the Gunicorn systemd service, reloads Nginx,
and optionally streams service logs.

Options:
  --follow          Stream Gunicorn systemd logs after restart.
  --no-follow       Exit after restart completes (default).
  --skip-static     Skip collectstatic.
  --skip-backup     Skip the database backup before applying pending migrations.
  --no-nginx        Skip nginx config validation and reload.
  -h, --help        Show this help text.

Environment:
  PYTHON_BIN=/path/to/python
  ENV_FILE=/path/to/.env
  DOMAIN=greenfish.calvinmazhindu.dev
  BASE_URL=https://greenfish.calvinmazhindu.dev
  GUNICORN_SERVICE=greenfish-gunicorn.service
  NGINX_SERVICE_NAME=nginx
  RUN_COMPRESS=1           Run manage.py compress before collectstatic.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow)
      FOLLOW=1
      shift
      ;;
    --no-follow)
      FOLLOW=0
      shift
      ;;
    --skip-static)
      COLLECTSTATIC=0
      shift
      ;;
    --skip-backup)
      SKIP_BACKUP=1
      shift
      ;;
    --no-nginx)
      RELOAD_NGINX=0
      shift
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
done

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python interpreter at $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file at $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$ROOT/manage.py" ]]; then
  echo "Cannot find manage.py in $ROOT" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export DJANGO_SETTINGS_MODULE="config.settings.production"
export APP_ENV="${APP_ENV:-production}"
export RELEASE_VERSION="${RELEASE_VERSION:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"

run_manage() {
  local label="$1"
  shift
  echo "${label}..."
  "$PYTHON_BIN" manage.py "$@"
}

run_sudo() {
  echo "+ sudo $*"
  sudo "$@"
}

echo "Restarting production release ${RELEASE_VERSION}"

run_manage "Running Django deployment checks" check --deploy
run_manage "Checking for missing migration files" makemigrations --check --dry-run

MIGRATIONS_PENDING=0
if "$PYTHON_BIN" manage.py migrate --check --noinput >/dev/null 2>&1; then
  echo "All database migrations are already applied."
else
  echo "Pending migrations detected."
  MIGRATIONS_PENDING=1
fi

if [[ "$MIGRATIONS_PENDING" == "1" ]]; then
  if [[ "$SKIP_BACKUP" == "1" ]]; then
    echo "WARNING: pending migrations detected; database backup skipped by request." >&2
  else
    echo "Pending migrations detected; backing up database before migrate..."
    if [[ -x "$ROOT/backup.sh" ]]; then
      "$ROOT/backup.sh"
    else
      echo "WARNING: backup.sh not found or not executable — skipping backup." >&2
    fi
  fi
  run_manage "Applying database migrations" migrate --noinput
fi

if [[ "$RUN_COMPRESS" == "1" ]]; then
  run_manage "Building offline compressed assets" compress --force
else
  echo "Skipping compressor step. Set RUN_COMPRESS=1 if compressor tags are added."
fi

if [[ "$COLLECTSTATIC" == "1" ]]; then
  run_manage "Collecting static files" collectstatic --noinput
else
  echo "Skipping collectstatic by request."
fi

if [[ "$RELOAD_NGINX" == "1" ]]; then
  echo "Validating Nginx configuration..."
  run_sudo nginx -t
fi

echo "Reloading systemd unit definitions..."
run_sudo systemctl daemon-reload

echo "Restarting ${GUNICORN_SERVICE}..."
run_sudo systemctl restart "$GUNICORN_SERVICE"
run_sudo systemctl --no-pager --full status "$GUNICORN_SERVICE" || true

if [[ "$RELOAD_NGINX" == "1" ]]; then
  echo "Reloading ${NGINX_SERVICE_NAME}..."
  run_sudo systemctl reload "$NGINX_SERVICE_NAME"
fi

HEALTH_URL="${HEALTH_URL:-${BASE_URL}/health/}"
if command -v curl >/dev/null 2>&1; then
  echo "Checking health endpoint ${HEALTH_URL}..."
  curl -fsS --max-time 10 "$HEALTH_URL" >/dev/null && echo "Health check passed." || echo "Health check failed." >&2
else
  echo "curl not found — skipping health check."
fi

echo "Production restart complete."

if [[ "$FOLLOW" == "1" ]]; then
  echo "Following ${GUNICORN_SERVICE} logs. Press Ctrl+C to stop watching; the service will keep running."
  exec sudo journalctl -fu "$GUNICORN_SERVICE"
fi
