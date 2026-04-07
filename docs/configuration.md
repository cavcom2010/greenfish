# Configuration Guide

Complete reference for all configuration options in Tinashe Takeaway.

## Environment Variables (.env)

### Django Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | None | **Required.** Secret key for cryptographic signing. Generate a new one for production. |
| `DJANGO_DEBUG` | False | Set to `True` for development, `False` for production. |
| `DJANGO_ALLOWED_HOSTS` | localhost,127.0.0.1 | Comma-separated list of allowed hostnames. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Empty | Comma-separated list of trusted origins for CSRF. Include `https://yourdomain.com`. |
| `TIME_ZONE` | Europe/London | Django timezone setting. |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Empty | PostgreSQL connection URL. Format: `postgres://user:pass@host:port/dbname`. Leave empty for SQLite. |
| `DB_CONN_MAX_AGE` | 60 | Database connection persistence in seconds. |
| `DB_SSL_REQUIRE` | False | Require SSL for database connections (recommended for production). |

### Mollie Payments

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLLIE_API_KEY` | None | **Required for payments.** Your Mollie API key. Use test key for development (starts with `test_`). |
| `MOLLIE_WEBHOOK_SECRET` | None | Secret for verifying webhooks. Generate a random string. |

**Getting Mollie API Keys:**
1. Sign up at https://www.mollie.com/dashboard
2. Go to Developers → API keys
3. Copy the Test key for development
4. Copy the Live key for production

### Email Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_BACKEND` | console.EmailBackend | Email backend. Use `smtp.EmailBackend` for production. |
| `EMAIL_HOST` | Empty | SMTP server hostname. |
| `EMAIL_PORT` | 587 | SMTP server port. |
| `EMAIL_USE_TLS` | True | Use TLS encryption for SMTP. |
| `EMAIL_HOST_USER` | Empty | SMTP username. |
| `EMAIL_HOST_PASSWORD` | Empty | SMTP password or app-specific password. |
| `DEFAULT_FROM_EMAIL` | orders@tinashe.com | Default sender email address. |

**Gmail SMTP Example:**
```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=Tinashe Takeaway <orders@tinashe.com>
```

### Shop Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOP_NAME` | Tinashe Takeaway | Name of your takeaway business. |
| `SHOP_ADDRESS` | 45 High Street | Full address displayed to customers. |
| `SHOP_PHONE` | Empty | Contact phone number. |
| `SHOP_EMAIL` | Empty | Contact email address. |
| `CURRENCY` | GBP | Currency code (GBP, EUR, USD). |

### Order Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ORDER_PREFIX` | TN | Prefix for order numbers (e.g., TN-12345). |
| `DEFAULT_PREP_TIME` | 15 | Default preparation time in minutes. |

### Security Settings (Production)

| Variable | Default | Description |
|----------|---------|-------------|
| `SECURE_SSL_REDIRECT` | True | Redirect all HTTP to HTTPS. |
| `SESSION_COOKIE_SECURE` | True | Only send session cookies over HTTPS. |
| `CSRF_COOKIE_SECURE` | True | Only send CSRF cookies over HTTPS. |
| `SECURE_HSTS_SECONDS` | 31536000 | HTTP Strict Transport Security max age (1 year). |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | True | Apply HSTS to subdomains. |
| `SECURE_HSTS_PRELOAD` | True | Allow domain to be preloaded in browsers. |

## Django Settings Files

### config/settings/base.py

Base settings shared across all environments. Don't modify this directly for local changes.

### config/settings/local.py

Development-specific settings:
- DEBUG = True
- SQLite database if DATABASE_URL not set
- Console email backend
- Disabled security settings for local testing

### config/settings/production.py

Production-specific settings:
- DEBUG = False
- Enforced HTTPS
- Security headers enabled
- File-based logging

## Customizing the UI

### Brand Colors

Edit `templates/base.html` and modify CSS variables:

```css
:root {
    --brand: #FF6B35;        /* Primary brand color */
    --brand-dark: #E55A2B;   /* Darker variant */
    --brand-light: #FFF0EB;  /* Light variant */
    --success: #22C55E;      /* Success states */
    --error: #EF4444;        /* Error states */
}
```

### Shop Logo

1. Go to Admin Panel → Core → Site Settings
2. Upload your logo (recommended: 200x50px PNG)
3. Upload favicon (32x32px PNG)

### Opening Hours

Set opening hours via Django Admin or shell:

```python
from apps.core.models import SiteSettings
settings = SiteSettings.get()
settings.opening_hours = {
    "0": {"open": "09:00", "close": "22:00"},  # Monday
    "1": {"open": "09:00", "close": "22:00"},  # Tuesday
    "2": {"open": "09:00", "close": "22:00"},  # Wednesday
    "3": {"open": "09:00", "close": "22:00"},  # Thursday
    "4": {"open": "09:00", "close": "23:00"},  # Friday
    "5": {"open": "10:00", "close": "23:00"},  # Saturday
    "6": {"open": "10:00", "close": "21:00"},  # Sunday
}
settings.save()
```

## Port Configuration

The home server uses these ports:

| Port | Purpose |
|------|---------|
| 8006 | Nginx (public-facing) |
| 8026 | Gunicorn (application server) |

To change ports, set environment variables before running start.sh:

```bash
export HOME_PORT=8080        # Change Nginx port
export HOME_APP_PORT=9000    # Change Gunicorn port
./deploy/home/start.sh
```

## Static and Media Files

### Static Files (CSS, JS, Icons)

- **Source**: `static/`
- **Collected**: `staticfiles/`
- **URL**: `/static/`

### Media Files (Uploads)

- **Storage**: `media/`
- **URL**: `/media/`
- **Types**: Menu item images, shop logo, offer images

**Production Note**: Configure a CDN or S3 bucket for media files in production.

## Logging

Logs are stored in `.home_nginx/logs/`:

- `gunicorn-access.log` - HTTP requests
- `gunicorn-error.log` - Application errors
- `error.log` - Nginx errors
- `access.log` - Nginx access log

View logs:

```bash
tail -f .home_nginx/logs/gunicorn-error.log
```
