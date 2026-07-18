# Production Deployment Guide

## Overview

This guide covers deploying the Restaurant Ordering System to a production server.

## Server Requirements

- Ubuntu 22.04 LTS (recommended)
- 2GB RAM minimum (4GB recommended)
- 20GB disk space
- Domain name with SSL certificate

## Step-by-Step Deployment

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv nginx postgresql redis-server git

# Create deployment user
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG sudo deploy
```

### 2. Database Setup

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database
CREATE DATABASE restaurant_db;
CREATE USER dbuser WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE restaurant_db TO dbuser;
\q
```

### 3. Application Setup

```bash
# Switch to deploy user
su - deploy

# Clone repository
cd ~
git clone <your-repo-url> restaurant-app
cd restaurant-app

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install psycopg2-binary gunicorn

# Configure environment
cp .env.example .env
# Edit .env with production values
nano .env
```

### 4. Environment Configuration

Edit `.env`:

```bash
DJANGO_SECRET_KEY=<generate-random-key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgres://dbuser:secure_password@localhost:5432/restaurant_db
PAYMENT_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx
# Customer checkout prefers online payment. If fallback is enabled, schedule expire_unpaid_orders and train staff to mark paid before preparation.
# ... other settings
```

### 5. Initialize Application

```bash
# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser

# Initialize site settings
python manage.py shell <<EOF
from apps.core.models import SiteSettings
settings = SiteSettings.get()
settings.shop_name = "Your Restaurant"
settings.save()
EOF
```

### 6. Gunicorn Setup

Create `/etc/systemd/system/restaurant-app.service`:

```ini
[Unit]
Description=Restaurant Ordering System
After=network.target

[Service]
User=deploy
Group=deploy
WorkingDirectory=/home/deploy/restaurant-app
Environment="PATH=/home/deploy/restaurant-app/venv/bin"
EnvironmentFile=/home/deploy/restaurant-app/.env
ExecStart=/home/deploy/restaurant-app/venv/bin/gunicorn \
    --access-logfile - \
    --workers 3 \
    --bind unix:/run/restaurant-app.sock \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl start restaurant-app
sudo systemctl enable restaurant-app
```

### 7. Nginx Configuration

Create `/etc/nginx/sites-available/restaurant-app`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        root /home/deploy/restaurant-app;
    }
    
    location /media/ {
        root /home/deploy/restaurant-app;
    }
    
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/restaurant-app.sock;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/restaurant-app /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### 8. SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### 9. Backup Script

Create `/home/deploy/backup.sh`:

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/home/deploy/backups

mkdir -p $BACKUP_DIR

# Backup database
source /home/deploy/restaurant-app/venv/bin/activate
cd /home/deploy/restaurant-app
python manage.py dumpdata > $BACKUP_DIR/db_$DATE.json

# Backup media
tar -czf $BACKUP_DIR/media_$DATE.tar.gz media/

# Keep only last 7 days
find $BACKUP_DIR -name "*.json" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

Make executable and schedule:

```bash
chmod +x /home/deploy/backup.sh
# Add to crontab
echo "0 2 * * * /home/deploy/backup.sh" | crontab -
```

### 10. Monitoring (Optional)

Install fail2ban:

```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

## Post-Deployment Verification

Checklist:

- [ ] Website loads with HTTPS
- [ ] Admin panel accessible
- [ ] Menu items display correctly
- [ ] Add to cart works
- [ ] Checkout flow completes
- [ ] Payment processes
- [ ] SMS notifications sent
- [ ] Kitchen board shows orders
- [ ] PWA installs correctly
- [ ] Backups running daily

## Troubleshooting

**Gunicorn won't start**
```bash
sudo journalctl -u restaurant-app
```

**Nginx errors**
```bash
sudo tail -f /var/log/nginx/error.log
```

**Permission issues**
```bash
sudo chown -R deploy:deploy /home/deploy/restaurant-app
```

## Updates

To update the application:

```bash
su - deploy
cd ~/restaurant-app
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart restaurant-app
```
