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

### Payments

| Variable | Default | Description |
|----------|---------|-------------|
| `PAYMENT_PROVIDER` | `stripe` | Active payment provider. Supported values: `stripe`, `mollie`. |
| `STRIPE_SECRET_KEY` | None | **Required when `PAYMENT_PROVIDER=stripe`.** Your Stripe secret key. |
| `STRIPE_PUBLISHABLE_KEY` | Empty | Optional publishable key for future frontend Stripe work. |
| `STRIPE_WEBHOOK_SECRET` | None | **Required when `PAYMENT_PROVIDER=stripe`.** Stripe webhook signing secret. |
| `MOLLIE_API_KEY` | Empty | Optional alternate provider key when `PAYMENT_PROVIDER=mollie`. |
| `MOLLIE_WEBHOOK_SECRET` | Empty | Optional alternate provider webhook secret when `PAYMENT_PROVIDER=mollie`. |
| `PAYMENT_FALLBACK_ENABLED` | `True` | Allow held unpaid orders when online payment is unavailable. |
| `PAYMENT_FALLBACK_HOLD_MINUTES` | `15` | Minutes before unpaid fallback orders are cancelled by `expire_unpaid_orders`. |

**Stripe setup:**
1. Create a Stripe account and get your API keys from Developers → API keys.
2. Set `PAYMENT_PROVIDER=stripe`.
3. Add `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.
4. Point your Stripe webhook endpoint to `/payments/webhook/`.

**Optional Mollie fallback:**
1. Keep your Mollie keys in `.env`, but leave `PAYMENT_PROVIDER=stripe` while Stripe is active.
2. Switch `PAYMENT_PROVIDER=mollie` only when you want to route checkout through Mollie again.

Customer checkout prefers online payment. If Stripe/Mollie is unavailable and `PAYMENT_FALLBACK_ENABLED=True`, customers can explicitly place an unpaid held order and must call or visit the shop to pay within `PAYMENT_FALLBACK_HOLD_MINUTES`; the kitchen must not prepare it until staff mark it paid.

### Email Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_BACKEND` | Empty/console | Optional backend override. If SMTP/provider credentials are missing, production prints emails to the shell with Django's console backend. |
| `EMAIL_HOST` | Empty | SMTP server hostname. Leave empty for shell/console email output. |
| `EMAIL_PORT` | 587 | SMTP server port. |
| `EMAIL_USE_TLS` | True | Use TLS encryption for SMTP. |
| `EMAIL_HOST_USER` | Empty | SMTP username. Leave empty for shell/console email output. |
| `EMAIL_HOST_PASSWORD` | Empty | SMTP password or app-specific password. Leave empty for shell/console email output. |
| `DEFAULT_FROM_EMAIL` | orders@tinashe.com | Default sender email address. |
| `SENDGRID_API_KEY` | Empty | Reserved for SendGrid integration. Missing key does not block startup. |
| `SENDER_NET_API_KEY` | Empty | Optional marketing email key. Missing key logs newsletter signups instead of calling Sender.net. |

**Fallback behavior:** if SMTP/SendGrid/Sender.net credentials are absent, all Django emails are printed to the shell/console and marketing signup activity is logged.

**Gmail SMTP Example:**
```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
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
| `DELIVERY_ENABLED` | True | Deployment-level delivery switch. Set to `False` to force pickup only, regardless of the admin setting. |
| `DELIVERY_MINIMUM_ORDER_AMOUNT` | 15.00 | Delivery food-subtotal minimum fallback when Admin → Site Settings does not define one. Set admin value or env value to `0.00` to disable. |
| `GOOGLE_MAPS_API_KEY` | Empty | Browser-restricted Google Maps key for checkout map loading and Places address search. |
| `GOOGLE_MAPS_MAP_ID` | Empty | Optional Google Maps cloud-styled/vector map ID for a polished checkout map. |
| `GOOGLE_MAPS_SERVER_API_KEY` | Empty | Optional server-restricted Google key for Address Validation API. Do not expose this key in templates. |
| `GOOGLE_ADDRESS_VALIDATION_ENABLED` | False | Set to `True` to run server-side Google Address Validation before local delivery-radius validation. |
| `GOOGLE_ADDRESS_VALIDATION_TIMEOUT_SECONDS` | 4 | Timeout for the optional server-side Address Validation request. |
| `SHOP_LATITUDE` | Empty | Shop latitude fallback when Admin → Site Settings does not define coordinates. |
| `SHOP_LONGITUDE` | Empty | Shop longitude fallback when Admin → Site Settings does not define coordinates. |
| `DELIVERY_RADIUS_MILES` | 3 | Delivery radius fallback when Admin → Site Settings does not define a radius. |

Delivery also has admin controls at Admin Panel → Core → Site Settings → Settings. Delivery is available only when both `DELIVERY_ENABLED=True` and the admin checkbox is enabled. The delivery minimum spend is checked against food subtotal before discounts; the admin value wins, and a blank admin value uses `DELIVERY_MINIMUM_ORDER_AMOUNT` from `.env`. When either delivery switch is off, customer-facing order screens become pickup-only and delivery labels/address fields are removed from the public UI; existing delivery-order history and staff workflows remain available.

Google Maps delivery checks are enabled only when delivery is enabled, Admin → Site Settings → Delivery Map is enabled, `GOOGLE_MAPS_API_KEY` is present, and shop coordinates are configured either in admin or `.env`. When Maps is not configured, checkout shows a professional manual address panel and staff confirm delivery details before preparation.

For production Google setup, create two keys in Google Cloud. Restrict `GOOGLE_MAPS_API_KEY` to the public site domains and only the browser APIs needed by checkout, including Maps JavaScript API and Places API. Restrict `GOOGLE_MAPS_SERVER_API_KEY` to the server/IP and Address Validation API, then set `GOOGLE_ADDRESS_VALIDATION_ENABLED=True` if you want Google's server-side address quality check before the existing local radius check.

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

If `HOME_APP_PORT` is occupied when you start the home server, `start.sh`
will move Gunicorn to the next available port above the requested one and
persist that choice for the matching stop script.

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


### Expiring unpaid fallback orders

When `PAYMENT_FALLBACK_ENABLED=True`, schedule this command every minute in production so unpaid held orders are cancelled after the hold window:

```bash
python manage.py expire_unpaid_orders
```

Use `python manage.py expire_unpaid_orders --dry-run` to check how many orders would expire without changing data.
