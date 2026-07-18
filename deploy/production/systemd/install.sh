#!/usr/bin/env bash
# Install the GreenFish celery worker + beat systemd units, templated to the
# actual repo path and user on this server.
#
# Usage (on the production server, from anywhere):
#   sudo bash deploy/production/systemd/install.sh
#
# Options:
#   --user NAME       Run services as this user (default: owner of the repo)
#   --group NAME      Run services as this group (default: primary group of user)
#   --with-gunicorn   Also install the gunicorn socket+service units
#   --dry-run         Print the rendered units without installing anything

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"

TEMPLATE_PATH="/home/deploy/greenfish"
TEMPLATE_USER="deploy"
TEMPLATE_GROUP="www-data"

RUN_USER="$(stat -c '%U' "$ROOT")"
RUN_GROUP="$(id -gn "$RUN_USER")"
WITH_GUNICORN=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) RUN_USER="$2"; RUN_GROUP="$(id -gn "$RUN_USER")"; shift 2 ;;
    --group) RUN_GROUP="$2"; shift 2 ;;
    --with-gunicorn) WITH_GUNICORN=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -x "$ROOT/venv/bin/celery" ]]; then
  echo "ERROR: $ROOT/venv/bin/celery not found. Run: venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

UNITS=(greenfish-celery.service greenfish-celerybeat.service)
if [[ "$WITH_GUNICORN" == "1" ]]; then
  UNITS+=(greenfish-gunicorn.socket greenfish-gunicorn.service)
fi

render() {
  sed -e "s|$TEMPLATE_PATH|$ROOT|g" \
      -e "s|^User=$TEMPLATE_USER|User=$RUN_USER|" \
      -e "s|^Group=$TEMPLATE_GROUP|Group=$RUN_GROUP|" \
      "$1"
}

echo "Repo:  $ROOT"
echo "User:  $RUN_USER"
echo "Group: $RUN_GROUP"
echo "Units: ${UNITS[*]}"
echo

if [[ "$DRY_RUN" == "1" ]]; then
  for unit in "${UNITS[@]}"; do
    echo "===== $unit ====="
    render "$HERE/$unit"
    echo
  done
  exit 0
fi

if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: installing units needs root. Re-run with: sudo bash $0" >&2
  exit 1
fi

for unit in "${UNITS[@]}"; do
  render "$HERE/$unit" > "/etc/systemd/system/$unit"
  echo "Installed /etc/systemd/system/$unit"
done

systemctl daemon-reload
for unit in "${UNITS[@]}"; do
  systemctl enable --now "$unit"
done

echo
for unit in "${UNITS[@]}"; do
  printf '%-32s %s\n' "$unit" "$(systemctl is-active "$unit")"
done

echo
echo "Follow logs with:"
echo "  journalctl -fu greenfish-celery -u greenfish-celerybeat"
