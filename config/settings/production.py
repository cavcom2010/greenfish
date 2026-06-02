"""
Production settings for Tinashe Takeaway.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *
from .payment_credentials import mollie_credentials_configured, stripe_credentials_configured

DEBUG = False


def _is_strong_secret_key(value):
    return bool(
        value
        and len(value) >= 50
        and len(set(value)) >= 5
        and not value.startswith("django-insecure-")
    )


ENFORCE_STRONG_SECRET_KEY = env("DJANGO_ENFORCE_STRONG_SECRET_KEY", default=True, cast=bool)
ALLOW_SQLITE_PRODUCTION = env("ALLOW_SQLITE_PRODUCTION", default=False, cast=bool)

if SECRET_KEY == "django-insecure-change-me-for-production":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")
if ENFORCE_STRONG_SECRET_KEY and not _is_strong_secret_key(SECRET_KEY):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong production secret.")

if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["localhost", "127.0.0.1"]:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set for production.")
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3" and not ALLOW_SQLITE_PRODUCTION:
    raise ImproperlyConfigured("DATABASE_URL must point to PostgreSQL in production.")

if PAYMENT_PROVIDER not in {"stripe", "mollie"}:
    raise ImproperlyConfigured("PAYMENT_PROVIDER must be either 'stripe' or 'mollie'.")
if PAYMENT_PROVIDER == "stripe":
    if not stripe_credentials_configured(STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET) and not PAYMENT_FALLBACK_ENABLED:
        raise ImproperlyConfigured("Valid Stripe credentials are required when payment fallback is disabled.")
elif PAYMENT_PROVIDER == "mollie":
    if not mollie_credentials_configured(MOLLIE_API_KEY, MOLLIE_WEBHOOK_SECRET) and not PAYMENT_FALLBACK_ENABLED:
        raise ImproperlyConfigured("Valid Mollie credentials are required when payment fallback is disabled.")

# Security settings
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE", default=True, cast=bool)
SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool)
SECURE_HSTS_PRELOAD = env("SECURE_HSTS_PRELOAD", default=True, cast=bool)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_REFERRER_POLICY = "same-origin"

# Email backend for production. If no external provider credentials are present,
# emails are printed to the shell via Django's console backend.
CONSOLE_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
SMTP_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_BACKEND_OVERRIDE = env("EMAIL_BACKEND", default="").strip()
SMTP_EMAIL_CONFIGURED = bool(EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD)
SENDGRID_CONFIGURED = bool(SENDGRID_API_KEY)
SENDER_NET_CONFIGURED = bool(SENDER_NET_API_KEY)

if SMTP_EMAIL_CONFIGURED and EMAIL_BACKEND_OVERRIDE:
    EMAIL_BACKEND = EMAIL_BACKEND_OVERRIDE
elif SMTP_EMAIL_CONFIGURED:
    EMAIL_BACKEND = SMTP_EMAIL_BACKEND
else:
    EMAIL_BACKEND = CONSOLE_EMAIL_BACKEND

# Static files
MIDDLEWARE = ["whitenoise.middleware.WhiteNoiseMiddleware"] + MIDDLEWARE
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
WHITENOISE_MAX_AGE = 31536000

# Logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOG_DIR / "django.log",
    "maxBytes": 1024 * 1024 * 5,  # 5 MB
    "backupCount": 5,
    "formatter": "verbose",
}
LOGGING["root"]["handlers"] = ["console", "file"]
