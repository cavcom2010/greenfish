"""
Production settings for Tinashe Takeaway.
"""
from .base import *

DEBUG = False

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

# Email backend for production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Static files - use whitenoise or CDN in production
# MIDDLEWARE = ["whitenoise.middleware.WhiteNoiseMiddleware"] + MIDDLEWARE
# STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Logging
LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": BASE_DIR / "logs" / "django.log",
    "maxBytes": 1024 * 1024 * 5,  # 5 MB
    "backupCount": 5,
    "formatter": "verbose",
}
LOGGING["root"]["handlers"] = ["console", "file"]
