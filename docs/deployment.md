# Deployment Guide

Complete guide for deploying Tinashe Takeaway to DigitalOcean.

## Prerequisites

- DigitalOcean account
- Domain name (optional but recommended)
- Stripe account with live API keys

## Server Requirements

- Ubuntu 22.04 LTS
- 1GB RAM minimum (2GB recommended)
- 25GB SSD

## Step-by-Step Deployment

### 1. Create Droplet

1. Log into DigitalOcean
2. Click "Create" → "Droplets"
3. Choose Ubuntu 22.04 (LTS) x64
4. Select Basic plan ($6/month or higher)
5. Choose datacenter region closest to your customers
6. Add SSH key for authentication
7. Click "Create Droplet"

### 2. Initial Server Setup

SSH into your server:

```bash
ssh root@your_server_ip
```

Update system packages:

```bash
apt update && apt upgrade -y
```

Install required packages:

```bash
apt install -y python3-pip python3-venv python3-dev nginx postgresql postgresql-contrib redis-server git certbot python3-certbot-nginx
```

### 3. Create PostgreSQL Database

```bash
sudo -u postgres psql
```

Create database and user:

```sql
CREATE DATABASE tinashe_takeaway;
CREATE USER tinashe_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE tinashe_takeaway TO tinashe_user;
\q
```

### 4. Create Application User

```bash
useradd -m -s /bin/bash tinashe
usermod -aG sudo tinashe
su - tinashe
```

### 5. Clone and Setup Application

```bash
cd ~
git clone https://github.com/yourusername/tinashe-takeaway.git
# Or upload via SCP/SFTP
cd tinashe-takeaway

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 6. Configure Environment

Create production .env file:

```bash
nano .env
```

Add production configuration:

```bash
# Django
DJANGO_SECRET_KEY=generate-a-secure-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,your_server_ip
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Database
DATABASE_URL=postgres://tinashe_user:your_secure_password@localhost:5432/tinashe_takeaway

# Payments
PAYMENT_PROVIDER=stripe

# Stripe Payments (LIVE KEY for production)
STRIPE_SECRET_KEY=sk_live_your_live_key_here
STRIPE_PUBLISHABLE_KEY=pk_live_your_publishable_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_signing_secret

# Mollie Payments (optional alternate provider)
MOLLIE_API_KEY=
MOLLIE_WEBHOOK_SECRET=

# Email (use real SMTP)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=Tinashe Takeaway <orders@tinashe.com>

# Shop Settings
SHOP_NAME=Tinashe Takeaway
SHOP_ADDRESS=45 High Street, Your Town
SHOP_PHONE=+44 123 456 7890
SHOP_EMAIL=orders@tinashe.com
CURRENCY=GBP
TIME_ZONE=Europe/London

# Order Settings
ORDER_PREFIX=TN
DEFAULT_PREP_TIME=15

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

### 7. Run Migrations and Collect Static

```bash
python manage.py migrate --settings=config.settings.production
python manage.py collectstatic --noinput --settings=config.settings.production
python manage.py createsuperuser --settings=config.settings.production
```

### 8. Create Systemd Service

Create service file:

```bash
sudo nano /etc/systemd/system/tinashe.service
```

Add:

```ini
[Unit]
Description=Tinashe Takeaway Gunicorn
After=network.target

[Service]
User=tinashe
Group=www-data
WorkingDirectory=/home/tinashe/tinashe-takeaway
EnvironmentFile=/home/tinashe/tinashe-takeaway/.env
ExecStart=/home/tinashe/tinashe-takeaway/venv/bin/gunicorn --access-logfile - --workers 3 --bind unix:/home/tinashe/tinashe-takeaway/app.sock config.wsgi:application

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl start tinashe
sudo systemctl enable tinashe
sudo systemctl status tinashe
```

### 9. Configure Nginx

Remove default site:

```bash
sudo rm /etc/nginx/sites-enabled/default
```

Create new config:

```bash
sudo nano /etc/nginx/sites-available/tinashe
```

Add:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com your_server_ip;

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        root /home/tinashe/tinashe-takeaway;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }

    location /media/ {
        root /home/tinashe/tinashe-takeaway;
        expires 1d;
        add_header Cache-Control "public, max-age=86400";
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/tinashe/tinashe-takeaway/app.sock;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/tinashe /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### 10. Setup SSL Certificate

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Follow prompts to configure HTTPS.

### 11. Configure Firewall

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
```

### 12. Final Checks

Test your deployment:

```bash
curl -I https://yourdomain.com
```

Visit:
- https://yourdomain.com - Customer app
- https://yourdomain.com/admin/ - Admin panel
- https://yourdomain.com/orders/dashboard/ - Order board

## Updating the Application

To deploy updates:

```bash
ssh tinashe@your_server_ip
cd ~/tinashe-takeaway
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=config.settings.production
python manage.py collectstatic --noinput --settings=config.settings.production
sudo systemctl restart tinashe
```

## Monitoring

### Check Service Status

```bash
sudo systemctl status tinashe
sudo systemctl status nginx
```

### View Logs

```bash
# Application logs
sudo journalctl -u tinashe -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Database Backups

Create backup script:

```bash
#!/bin/bash
# /home/tinashe/backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump tinashe_takeaway > /home/tinashe/backups/tinashe_backup_$DATE.sql
find /home/tinashe/backups -name "*.sql" -mtime +7 -delete
```

Add to crontab:

```bash
crontab -e
# Add: 0 2 * * * /home/tinashe/backup.sh
```

## Troubleshooting

See [Troubleshooting Guide](troubleshooting.md) for common issues.

## SSL Renewal

Certbot auto-renews certificates. Test renewal:

```bash
sudo certbot renew --dry-run
```

## Performance Tuning

For high traffic, consider:

1. Increase Gunicorn workers: `--workers 5`
2. Enable PostgreSQL connection pooling
3. Use Redis for caching
4. Configure CDN for static/media files
5. Add server monitoring (e.g., New Relic, Datadog)
