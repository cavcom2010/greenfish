#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_NAME="${APP_NAME:-Tinashe Takeaway}"

PYTHON_BIN="$ROOT/venv/bin/python"
GUNICORN_BIN="$ROOT/venv/bin/gunicorn"

print_usage() {
  cat <<'EOF'
Usage: ./deploy/home/start.sh [--foreground|--daemon] [--help]

Options:
  --foreground  Keep Gunicorn attached to this terminal and stream logs live (default).
  --daemon      Run Gunicorn detached in the background and write logs to disk.
  --help        Show this help text.

Environment:
  HOME_FOREGROUND=1  Same as --foreground (default).
  HOME_FOREGROUND=0  Same as --daemon.
  HOME_CLIENT_MAX_BODY_SIZE=8m  Nginx request body limit for uploads.
  HOME_APP_PORT=8026  Requested Gunicorn port. If occupied, start.sh uses the
                       next free port above it and records that choice for stop.sh.

Home server for ${APP_NAME} - runs on port :8026
EOF
}

if [[ ! -x "$PYTHON_BIN" ]] || [[ ! -x "$GUNICORN_BIN" ]]; then
  echo "Missing venv binaries at $ROOT/venv. Activate/create your venv first." >&2
  exit 1
fi

case "${HOME_FOREGROUND:-1}" in
  1|true|TRUE|yes|YES|on|ON)
    HOME_FOREGROUND_MODE=1
    ;;
  0|false|FALSE|no|NO|off|OFF)
    HOME_FOREGROUND_MODE=0
    ;;
  *)
    echo "Invalid HOME_FOREGROUND value: ${HOME_FOREGROUND}" >&2
    exit 1
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground)
      HOME_FOREGROUND_MODE=1
      ;;
    --daemon)
      HOME_FOREGROUND_MODE=0
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

export DJANGO_SETTINGS_MODULE="${HOME_DJANGO_SETTINGS_MODULE:-${DJANGO_SETTINGS_MODULE:-config.settings.production}}"
export ALLOW_SQLITE_PRODUCTION="${ALLOW_SQLITE_PRODUCTION:-1}"
export DJANGO_ENFORCE_STRONG_SECRET_KEY="${DJANGO_ENFORCE_STRONG_SECRET_KEY:-0}"

# Intentionally do not source .env here.
# python-decouple reads .env directly and shell-sourcing can break on non-bash-safe values.

HOME_DIR="$ROOT/.home_nginx"
LOG_DIR="$HOME_DIR/logs"
RUN_DIR="$HOME_DIR/run"
TMP_DIR="$HOME_DIR/tmp"
HOME_CLIENT_MAX_BODY_SIZE="${HOME_CLIENT_MAX_BODY_SIZE:-8m}"

mkdir -p "$LOG_DIR" "$RUN_DIR"
mkdir -p "$TMP_DIR/client_body" "$TMP_DIR/proxy" "$TMP_DIR/fastcgi" "$TMP_DIR/uwsgi" "$TMP_DIR/scgi"

detect_lan_ip() {
  local ip=""

  if [[ -n "${HOME_INTERFACE:-}" ]]; then
    ip="$(ip -o -4 addr show dev "${HOME_INTERFACE}" scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1 || true)"
  fi

  if [[ -z "$ip" ]]; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<NF; i++) if ($i=="src") {print $(i+1); exit}}' || true)"
  fi

  if [[ -z "$ip" ]]; then
    ip="$(hostname -I 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i !~ /^127\./) {print $i; exit}}' || true)"
  fi

  if [[ -z "$ip" ]]; then
    ip="127.0.0.1"
  fi

  printf '%s' "$ip"
}

normalize_csv_unique() {
  local raw="$1"
  local out=""
  local token=""
  declare -A seen=()
  IFS=',' read -ra parts <<< "$raw"
  for token in "${parts[@]}"; do
    token="${token#"${token%%[![:space:]]*}"}"
    token="${token%"${token##*[![:space:]]}"}"
    [[ -z "$token" ]] && continue
    if [[ -z "${seen[$token]+x}" ]]; then
      seen["$token"]=1
      if [[ -z "$out" ]]; then
        out="$token"
      else
        out="${out},${token}"
      fi
    fi
  done
  printf '%s' "$out"
}

kill_pid_tree() {
  local pid="$1"
  local child_pids=""
  child_pids="$(pgrep -P "$pid" || true)"

  kill -TERM "$pid" 2>/dev/null || true
  if [[ -n "$child_pids" ]]; then
    kill -TERM $child_pids 2>/dev/null || true
  fi

  for _ in {1..25}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
  fi

  if [[ -n "$child_pids" ]]; then
    for child_pid in $child_pids; do
      if kill -0 "$child_pid" 2>/dev/null; then
        kill -KILL "$child_pid" 2>/dev/null || true
      fi
    done
  fi
}

port_in_use() {
  ss -ltn "sport = :$1" | awk 'NR>1 {print $4}' | grep -q ":$1$"
}

find_next_free_port() {
  local port="$1"

  while port_in_use "$port"; do
    ((port++))
    if (( port > 65535 )); then
      echo "No free port found before 65535." >&2
      return 1
    fi
  done

  printf '%s' "$port"
}

wait_for_port() {
  local port="$1"

  for _ in {1..50}; do
    if port_in_use "$port"; then
      return 0
    fi
    sleep 0.2
  done

  return 1
}

read_pid_file() {
  local pid_file="$1"
  local pid=""

  [[ -f "$pid_file" ]] || return 1
  pid="$(tr -dc '0-9' < "$pid_file")"
  [[ -n "$pid" ]] || return 1

  printf '%s' "$pid"
}

read_port_file() {
  local port_file="$1"
  local port=""

  [[ -f "$port_file" ]] || return 1
  port="$(tr -dc '0-9' < "$port_file")"
  [[ -n "$port" ]] || return 1

  printf '%s' "$port"
}

pid_is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

kill_listeners_on_port() {
  local port="$1"
  local pids=""
  pids="$(ss -ltnp "( sport = :${port} )" 2>/dev/null | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true)"
  [[ -z "$pids" ]] && return 0

  kill $pids 2>/dev/null || true
  sleep 0.5

  local still_up=""
  still_up="$(ss -ltnp "( sport = :${port} )" 2>/dev/null | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true)"
  [[ -z "$still_up" ]] || kill -9 $still_up 2>/dev/null || true
}

LAN_IP="${HOME_HOST:-$(detect_lan_ip)}"
HOME_BIND="${HOME_BIND:-0.0.0.0}"

# Port configuration for ${APP_NAME}
NGINX_PORT="${HOME_PORT:-8006}"
REQUESTED_GUNICORN_PORT="${HOME_APP_PORT:-8026}"
GUNICORN_PORT="$(find_next_free_port "$REQUESTED_GUNICORN_PORT")"
GUNICORN_WORKERS="${HOME_GUNICORN_WORKERS:-3}"
GUNICORN_TIMEOUT="${HOME_GUNICORN_TIMEOUT:-120}"
APP_MODULE="${HOME_APP_MODULE:-${GUNICORN_APP_MODULE:-config.wsgi:application}}"
COLLECTSTATIC="${HOME_COLLECTSTATIC:-1}"
FORCE_RESTART="${HOME_FORCE_RESTART:-1}"
RUN_MANAGE_CHECK="${HOME_RUN_MANAGE_CHECK:-1}"
CHECK_MODEL_MIGRATIONS="${HOME_CHECK_MODEL_MIGRATIONS:-1}"
RUN_MIGRATIONS="${HOME_RUN_MIGRATIONS:-1}"

GUNICORN_PID="$RUN_DIR/gunicorn.pid"
GUNICORN_PORT_FILE="$RUN_DIR/gunicorn.port"
NGINX_PID="$RUN_DIR/nginx.pid"
HOME_HOST_FILE="$RUN_DIR/home_host"
HOME_SCHEME_FILE="$RUN_DIR/home_scheme"
FOREGROUND_GUNICORN_PID=""
FOREGROUND_NGINX_TAIL_PID=""
FOREGROUND_CLEANED_UP=0

stop_foreground_services() {
  local gunicorn_pid="${FOREGROUND_GUNICORN_PID}"

  [[ "$FOREGROUND_CLEANED_UP" == "1" ]] && return
  FOREGROUND_CLEANED_UP=1

  if [[ -z "$gunicorn_pid" ]] && [[ -f "$GUNICORN_PID" ]]; then
    gunicorn_pid="$(tr -dc '0-9' < "$GUNICORN_PID")"
  fi

  if [[ -n "$gunicorn_pid" ]] && kill -0 "$gunicorn_pid" 2>/dev/null; then
    echo
    echo "Stopping foreground Gunicorn (pid ${gunicorn_pid})..."
    kill_pid_tree "$gunicorn_pid"
  fi
  rm -f "$GUNICORN_PID"
  rm -f "$GUNICORN_PORT_FILE"

  if [[ -f "$NGINX_PID" ]] || port_in_use "$NGINX_PORT"; then
    echo "Stopping Nginx..."
    nginx -p "$HOME_DIR" -c "$HOME_DIR/nginx.conf" -s stop 2>/dev/null || true
    rm -f "$NGINX_PID"
    kill_listeners_on_port "$NGINX_PORT"
  fi

  if [[ -n "$FOREGROUND_NGINX_TAIL_PID" ]] && kill -0 "$FOREGROUND_NGINX_TAIL_PID" 2>/dev/null; then
    kill "$FOREGROUND_NGINX_TAIL_PID" 2>/dev/null || true
    wait "$FOREGROUND_NGINX_TAIL_PID" 2>/dev/null || true
  fi

  rm -f "$HOME_HOST_FILE" "$HOME_SCHEME_FILE"
}

handle_foreground_exit() {
  stop_foreground_services
}

handle_foreground_interrupt() {
  trap - EXIT INT TERM
  stop_foreground_services
  exit 130
}

handle_foreground_term() {
  trap - EXIT INT TERM
  stop_foreground_services
  exit 143
}

# Keep LAN mode HTTP-first and avoid HTTPS redirect/cookie surprises.
export SECURE_SSL_REDIRECT="${HOME_SECURE_SSL_REDIRECT:-false}"
export SESSION_COOKIE_SECURE="${HOME_SESSION_COOKIE_SECURE:-false}"
export CSRF_COOKIE_SECURE="${HOME_CSRF_COOKIE_SECURE:-false}"
export SECURE_HSTS_SECONDS="${HOME_SECURE_HSTS_SECONDS:-0}"
export SECURE_HSTS_INCLUDE_SUBDOMAINS="${HOME_SECURE_HSTS_INCLUDE_SUBDOMAINS:-false}"
export SECURE_HSTS_PRELOAD="${HOME_SECURE_HSTS_PRELOAD:-false}"
export USE_X_FORWARDED_HOST="${HOME_USE_X_FORWARDED_HOST:-false}"
export USE_X_FORWARDED_PORT="${HOME_USE_X_FORWARDED_PORT:-false}"
export SECURE_PROXY_SSL_HEADER="${HOME_SECURE_PROXY_SSL_HEADER:-}"

ALLOWED_BASE="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
CSRF_BASE="${DJANGO_CSRF_TRUSTED_ORIGINS:-http://localhost,http://127.0.0.1}"
LOCAL_ORIGINS="http://localhost:${NGINX_PORT},http://127.0.0.1:${NGINX_PORT}"

export DJANGO_ALLOWED_HOSTS="$(normalize_csv_unique "${ALLOWED_BASE},${LAN_IP}")"
export DJANGO_CSRF_TRUSTED_ORIGINS="$(normalize_csv_unique "${CSRF_BASE},${LOCAL_ORIGINS},http://${LAN_IP}:${NGINX_PORT}")"

export ALLOWED_HOSTS="$DJANGO_ALLOWED_HOSTS"
export CSRF_TRUSTED_ORIGINS="$DJANGO_CSRF_TRUSTED_ORIGINS"

export SITE_PROTO="http"
export SITE_DOMAIN="${LAN_IP}:${NGINX_PORT}"

describe_server_state() {
  local gunicorn_pid=""
  local nginx_pid=""
  local server_running=1

  if gunicorn_pid="$(read_pid_file "$GUNICORN_PID" 2>/dev/null)" && pid_is_running "$gunicorn_pid"; then
    server_running=0
    echo "Gunicorn is running (pid ${gunicorn_pid})."
  else
    rm -f "$GUNICORN_PID"
    echo "Gunicorn is stopped."
  fi

  if nginx_pid="$(read_pid_file "$NGINX_PID" 2>/dev/null)" && pid_is_running "$nginx_pid"; then
    server_running=0
    echo "Nginx is running (pid ${nginx_pid})."
  else
    rm -f "$NGINX_PID"
    echo "Nginx is stopped."
  fi

  if port_in_use "$GUNICORN_PORT" || port_in_use "$NGINX_PORT"; then
    server_running=0
  fi

  if [[ "$server_running" -eq 0 ]]; then
    echo "Home server listeners are active."
  else
    echo "Home server is fully stopped."
  fi
}

run_manage_command() {
  local label="$1"
  shift

  echo "${label}..."
  "$PYTHON_BIN" manage.py "$@"
}

run_preflight_checks() {
  echo "Running Django preflight before restarting services..."

  if [[ "$RUN_MANAGE_CHECK" == "1" ]]; then
    run_manage_command "Running python manage.py check" check
  fi

  if [[ "$CHECK_MODEL_MIGRATIONS" == "1" ]]; then
    run_manage_command "Checking for missing migration files" makemigrations --check --dry-run
  fi

  if [[ "$RUN_MIGRATIONS" == "1" ]]; then
    if "$PYTHON_BIN" manage.py migrate --check --noinput >/dev/null 2>&1; then
      echo "Database migrations are already applied."
    else
      run_manage_command "Applying database migrations" migrate --noinput
    fi
  fi

  if [[ "$COLLECTSTATIC" == "1" ]]; then
    echo "Collecting static files..."
    "$PYTHON_BIN" manage.py collectstatic --noinput >/dev/null
  fi
}

describe_server_state
run_preflight_checks

if [[ "$FORCE_RESTART" == "1" ]]; then
  FORCE_RESTART_GUNICORN_PORT="$GUNICORN_PORT"
  if [[ -f "$GUNICORN_PORT_FILE" ]]; then
    FORCE_RESTART_GUNICORN_PORT="$(read_port_file "$GUNICORN_PORT_FILE" 2>/dev/null || printf '%s' "$GUNICORN_PORT")"
  fi

  if [[ -f "$NGINX_PID" ]] && pid_is_running "$(cat "$NGINX_PID")"; then
    echo "Stopping existing home Nginx (pid $(cat "$NGINX_PID"))..."
    nginx -p "$HOME_DIR" -c "$HOME_DIR/nginx.conf" -s stop 2>/dev/null || true
    rm -f "$NGINX_PID"
  fi

  if [[ -f "$GUNICORN_PID" ]] && pid_is_running "$(cat "$GUNICORN_PID")"; then
    echo "Stopping existing home Gunicorn (pid $(cat "$GUNICORN_PID"))..."
    kill_pid_tree "$(cat "$GUNICORN_PID")"
    rm -f "$GUNICORN_PID"
  fi

  kill_listeners_on_port "$NGINX_PORT"
  kill_listeners_on_port "$FORCE_RESTART_GUNICORN_PORT"
  rm -f "$GUNICORN_PORT_FILE"
fi

if [[ -f "$GUNICORN_PID" ]] && pid_is_running "$(cat "$GUNICORN_PID")"; then
  if [[ -f "$GUNICORN_PORT_FILE" ]]; then
    GUNICORN_PORT="$(read_port_file "$GUNICORN_PORT_FILE" 2>/dev/null || printf '%s' "$GUNICORN_PORT")"
  fi

  PREVIOUS_HOME_HOST=""
  if [[ -f "$HOME_HOST_FILE" ]]; then
    PREVIOUS_HOME_HOST="$(cat "$HOME_HOST_FILE" 2>/dev/null || true)"
  fi

  if [[ -n "$PREVIOUS_HOME_HOST" && "$PREVIOUS_HOME_HOST" != "$LAN_IP" ]]; then
    echo "LAN IP changed (${PREVIOUS_HOME_HOST} -> ${LAN_IP}); restarting Gunicorn..."
    kill_pid_tree "$(cat "$GUNICORN_PID")"
    rm -f "$GUNICORN_PID"
    rm -f "$GUNICORN_PORT_FILE"
  else
    echo "Gunicorn already running (pid $(cat "$GUNICORN_PID"))."
  fi
fi

if [[ "$HOME_FOREGROUND_MODE" == "1" ]] && [[ -f "$GUNICORN_PID" ]] && pid_is_running "$(cat "$GUNICORN_PID")"; then
  echo "Foreground mode requires a fresh Gunicorn process to attach live logs; restarting existing Gunicorn..."
  kill_pid_tree "$(cat "$GUNICORN_PID")"
  rm -f "$GUNICORN_PID"
  rm -f "$GUNICORN_PORT_FILE"
fi

if [[ ! -f "$GUNICORN_PID" ]] || ! pid_is_running "$(cat "$GUNICORN_PID")"; then
  rm -f "$GUNICORN_PID"
  rm -f "$GUNICORN_PORT_FILE"

  if [[ "$GUNICORN_PORT" != "$REQUESTED_GUNICORN_PORT" ]]; then
    echo "App port ${REQUESTED_GUNICORN_PORT} is already in use; using ${GUNICORN_PORT} instead."
  fi

  if [[ "$HOME_FOREGROUND_MODE" == "1" ]]; then
    trap handle_foreground_exit EXIT
    trap handle_foreground_interrupt INT
    trap handle_foreground_term TERM

    echo "Starting Gunicorn on 127.0.0.1:${GUNICORN_PORT} in foreground mode..."
    "$GUNICORN_BIN" \
      "$APP_MODULE" \
      --bind "127.0.0.1:${GUNICORN_PORT}" \
      --workers "$GUNICORN_WORKERS" \
      --timeout "$GUNICORN_TIMEOUT" \
      --access-logfile "-" \
      --error-logfile "-" \
      --capture-output \
      --log-level info \
      --pid "$GUNICORN_PID" &
    FOREGROUND_GUNICORN_PID="$!"
    printf '%s' "$GUNICORN_PORT" >"$GUNICORN_PORT_FILE"

    if ! wait_for_port "$GUNICORN_PORT"; then
      rm -f "$GUNICORN_PORT_FILE"
      echo "Gunicorn did not start listening on 127.0.0.1:${GUNICORN_PORT}." >&2
      exit 1
    fi
  else
    echo "Starting Gunicorn on 127.0.0.1:${GUNICORN_PORT}..."
    "$GUNICORN_BIN" \
      "$APP_MODULE" \
      --bind "127.0.0.1:${GUNICORN_PORT}" \
      --workers "$GUNICORN_WORKERS" \
      --timeout "$GUNICORN_TIMEOUT" \
      --access-logfile "$LOG_DIR/gunicorn-access.log" \
      --error-logfile "$LOG_DIR/gunicorn-error.log" \
      --capture-output \
      --log-level info \
      --daemon \
      --pid "$GUNICORN_PID"
    printf '%s' "$GUNICORN_PORT" >"$GUNICORN_PORT_FILE"
  fi
fi

STATIC_ROOT="$ROOT/staticfiles"
if [[ ! -d "$STATIC_ROOT" ]] || [[ -z "$(ls -A "$STATIC_ROOT" 2>/dev/null)" ]]; then
  STATIC_ROOT="$ROOT/static"
fi

MEDIA_ROOT="$ROOT/media"
NGINX_CONF="$HOME_DIR/nginx.conf"

if [[ "$HOME_FOREGROUND_MODE" == "1" ]]; then
  touch "$LOG_DIR/access.log" "$LOG_DIR/error.log"
  tail -n 0 -v -F "$LOG_DIR/access.log" "$LOG_DIR/error.log" &
  FOREGROUND_NGINX_TAIL_PID="$!"
fi

cat >"$NGINX_CONF" <<EOF_NGINX
worker_processes  1;
pid run/nginx.pid;

events {
  worker_connections  1024;
}

http {
  include       /etc/nginx/mime.types;
  default_type  application/octet-stream;

  access_log  logs/access.log;
  error_log   logs/error.log info;
  sendfile    on;
  keepalive_timeout  65;

  client_body_temp_path tmp/client_body;
  proxy_temp_path tmp/proxy;
  fastcgi_temp_path tmp/fastcgi;
  uwsgi_temp_path tmp/uwsgi;
  scgi_temp_path tmp/scgi;

  upstream tinashe_app {
    server 127.0.0.1:${GUNICORN_PORT};
    keepalive 16;
  }

  server {
    listen ${HOME_BIND}:${NGINX_PORT};
    server_name _;

    client_max_body_size ${HOME_CLIENT_MAX_BODY_SIZE};

    location /static/ {
      alias ${STATIC_ROOT}/;
      expires 7d;
      add_header Cache-Control "public, max-age=604800";
    }

    location /media/ {
      alias ${MEDIA_ROOT}/;
      expires 1d;
      add_header Cache-Control "public, max-age=86400";
    }

    location / {
      proxy_pass http://tinashe_app;
      proxy_set_header Host \$http_host;
      proxy_set_header X-Real-IP \$remote_addr;
      proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto \$scheme;
      proxy_redirect off;
      proxy_read_timeout ${GUNICORN_TIMEOUT};
      proxy_send_timeout ${GUNICORN_TIMEOUT};
    }
  }
}
EOF_NGINX

echo "Starting Nginx on ${HOME_BIND}:${NGINX_PORT}..."
if [[ -f "$NGINX_PID" ]] && pid_is_running "$(cat "$NGINX_PID")"; then
  nginx -p "$HOME_DIR" -c "$NGINX_CONF" -s reload
else
  if port_in_use "$NGINX_PORT"; then
    echo "Port ${NGINX_PORT} is already in use. Stop the existing process and retry." >&2
    ss -ltnp "( sport = :${NGINX_PORT} )" || true
    exit 1
  fi
  nginx -p "$HOME_DIR" -c "$NGINX_CONF"
fi

printf '%s' "$LAN_IP" >"$HOME_HOST_FILE"
printf 'http' >"$HOME_SCHEME_FILE"

if command -v curl >/dev/null 2>&1; then
  HEALTHCHECK_HOST="127.0.0.1"
  if [[ "$HOME_BIND" != "0.0.0.0" && "$HOME_BIND" != "::" ]]; then
    HEALTHCHECK_HOST="$HOME_BIND"
  fi

  if ! curl -fsS --max-time 5 "http://${HEALTHCHECK_HOST}:${NGINX_PORT}/health/" >/dev/null; then
    echo "HTTP health check failed on ${HEALTHCHECK_HOST}:${NGINX_PORT}." >&2
    echo "Check .home_nginx/logs/error.log and .home_nginx/logs/gunicorn-error.log" >&2
    exit 1
  fi
fi

echo "Done."
echo "Open local: http://127.0.0.1:${NGINX_PORT}/"
echo "Open: http://${LAN_IP}:${NGINX_PORT}/"
echo "If your browser auto-upgrades LAN IPs to HTTPS, disable 'Always use secure connections' for local testing."

if [[ "$HOME_FOREGROUND_MODE" == "1" ]]; then
  echo "Foreground mode active. Gunicorn and Nginx logs will stream in this terminal. Press Ctrl+C to stop Gunicorn and Nginx."
  set +e
  wait "$FOREGROUND_GUNICORN_PID"
  GUNICORN_EXIT_CODE="$?"
  set -e
  trap - EXIT INT TERM
  stop_foreground_services
  exit "$GUNICORN_EXIT_CODE"
fi
