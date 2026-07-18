#!/bin/bash
# Backup script for Restaurant Ordering System.
#
# - PostgreSQL databases are dumped with pg_dump (custom format, restorable
#   with pg_restore). SQLite falls back to a JSON dumpdata export.
# - Media files are archived as tar.gz.
# - Secrets (.env) are intentionally NOT backed up by this script. Keep them
#   in your secret manager / password vault instead.
#
# Restore (PostgreSQL):  pg_restore --clean --no-owner -d "$DATABASE_URL" backups/db_<DATE>.pgdump
# Restore (SQLite/JSON): python manage.py loaddata backups/db_<DATE>.json
# Restore (media):       tar -xzf backups/media_<DATE>.tar.gz -C "$PROJECT_DIR"

set -euo pipefail

# Configuration
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory (owner-only: dumps contain customer data)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Activate virtual environment
source "$PROJECT_DIR/venv/bin/activate"

cd "$PROJECT_DIR"

# Read DATABASE_URL from .env without exporting the rest of the secrets.
DATABASE_URL="$(grep -E '^DATABASE_URL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"

# Database backup
echo "Backing up database..."
if [[ "$DATABASE_URL" == postgres* ]]; then
    pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" > "$BACKUP_DIR/db_$DATE.pgdump"
else
    python manage.py dumpdata --exclude auth.permission --exclude contenttypes > "$BACKUP_DIR/db_$DATE.json"
fi

# Media files backup
echo "Backing up media files..."
if [ -d "$PROJECT_DIR/media" ]; then
    tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" -C "$PROJECT_DIR" media/
fi

# Remove any legacy plaintext .env backups created by older versions of this script.
find "$BACKUP_DIR" -name "env_*.bak" -delete 2>/dev/null || true

# Clean old backups
echo "Cleaning old backups..."
find "$BACKUP_DIR" -name "*.json" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.pgdump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup complete: $DATE"
echo "Files saved to: $BACKUP_DIR"
