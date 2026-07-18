"""
Local development settings for Tinashe Takeaway.
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Local dev may use the fake demo checkout when Stripe keys are absent.
DEMO_CHECKOUT_ENABLED = env("DEMO_CHECKOUT_ENABLED", default=True, cast=bool)

# Email backend is inherited from base settings so .env can switch local
# development between console output and a local SMTP inbox such as Mailpit.

# Debug toolbar (optional)
# INSTALLED_APPS += ["debug_toolbar"]
# MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

# Disable security settings for local development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Console logging
LOGGING["handlers"]["console"]["level"] = "DEBUG"
LOGGING["root"]["level"] = "DEBUG"
