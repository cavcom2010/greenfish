#!/bin/bash
# Backup script for Restaurant Ordering System

# Configuration
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Activate virtual environment
source "$PROJECT_DIR/venv/bin/activate"

cd "$PROJECT_DIR"

# Database backup
echo "Backing up database..."
python manage.py dumpdata --exclude auth.permission --exclude contenttypes > "$BACKUP_DIR/db_$DATE.json"

# Media files backup
echo "Backing up media files..."
if [ -d "$PROJECT_DIR/media" ]; then
    tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" -C "$PROJECT_DIR" media/
fi

# Environment backup (optional - remove if sensitive)
echo "Backing up environment..."
cp "$PROJECT_DIR/.env" "$BACKUP_DIR/env_$DATE.bak"

# Clean old backups
echo "Cleaning old backups..."
find "$BACKUP_DIR" -name "*.json" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.bak" -mtime +$RETENTION_DAYS -delete

echo "Backup complete: $DATE"
echo "Files saved to: $BACKUP_DIR"
