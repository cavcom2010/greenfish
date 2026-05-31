"""
Base settings for Tinashe Takeaway.
"""
import os
from pathlib import Path

import dj_database_url
from decouple import AutoConfig, Config, RepositoryEnv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables
env_file = os.getenv("ENV_FILE", "").strip()
if env_file:
    env_path = Path(env_file).expanduser()
    if not env_path.is_absolute():
        env_path = BASE_DIR / env_path
    env = Config(RepositoryEnv(str(env_path)))
else:
    env = AutoConfig(search_path=BASE_DIR)

# Security
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-change-me-for-production")
DEBUG = env("DJANGO_DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = env(
    "DJANGO_ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# CSRF
CSRF_TRUSTED_ORIGINS = env(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default="",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()] if v else [],
)

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_htmx",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
]

LOCAL_APPS = [
    # Infrastructure
    "apps.core",           # Shared utilities
    "apps.config",         # Site settings
    
    # Identity
    "apps.accounts",       # Authentication + Customer profiles
    
    # Commerce
    "apps.menu",           # Product catalog
    "apps.cart",           # Shopping cart (session-based)
    "apps.orders",         # Order management
    "apps.operations",     # Staff operations boards
    "apps.payments",       # Payment processing
    
    # Marketing
    "apps.offers",         # Vouchers & promotions
    "apps.loyalty",        # Loyalty program
    "apps.sms",            # SMS notifications
    
    # Features
    "apps.mealdeals",      # Combo meals
    "apps.pwa",            # Progressive Web App
    "apps.analytics",      # Business intelligence
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.core.middleware.DesktopDetectionMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.config.context_processors.site_settings",
                "apps.core.context_processors.cart_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASE_URL = env("DATABASE_URL", default="").strip()
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=env("DB_CONN_MAX_AGE", default=60, cast=int),
            ssl_require=env("DB_SSL_REQUIRE", default=False, cast=bool),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("TIME_ZONE", default="Europe/London")
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = env("DATA_UPLOAD_MAX_MEMORY_SIZE", default=8 * 1024 * 1024, cast=int)
FILE_UPLOAD_MAX_MEMORY_SIZE = env("FILE_UPLOAD_MAX_MEMORY_SIZE", default=512 * 1024, cast=int)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env("DATA_UPLOAD_MAX_NUMBER_FIELDS", default=500, cast=int)
DATA_UPLOAD_MAX_NUMBER_FILES = env("DATA_UPLOAD_MAX_NUMBER_FILES", default=10, cast=int)

# Caching
CACHES = {
    "default": {
        "BACKEND": env(
            "DJANGO_CACHE_BACKEND",
            default="django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": env("DJANGO_CACHE_LOCATION", default="two_fish-default"),
    }
}

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Django AllAuth Configuration
ACCOUNT_ADAPTER = "apps.accounts.adapter.DesktopAwareAccountAdapter"
SITE_ID = 1
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = True

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

# Shop Settings
SHOP_NAME = env("SHOP_NAME", default="Tinashe Zimbabwean Kitchen")
SHOP_ADDRESS = env("SHOP_ADDRESS", default="123 High Street, Harare")
SHOP_PHONE = env("SHOP_PHONE", default="")
SHOP_EMAIL = env("SHOP_EMAIL", default="")
CURRENCY = env("CURRENCY", default="GBP")
ORDER_PREFIX = env("ORDER_PREFIX", default="TN")
DEFAULT_PREP_TIME = env("DEFAULT_PREP_TIME", default=15, cast=int)
DELIVERY_ENABLED = env("DELIVERY_ENABLED", default=True, cast=bool)

# Payment Provider Settings
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="stripe").strip().lower()
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# Mollie Settings
MOLLIE_API_KEY = env("MOLLIE_API_KEY", default="")
MOLLIE_WEBHOOK_SECRET = env("MOLLIE_WEBHOOK_SECRET", default="")

# Email Settings (Google Workspace SMTP — transactional emails)
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = env("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="orders@tinashe.com")

# SendGrid API — optional future transactional email provider.
SENDGRID_API_KEY = env("SENDGRID_API_KEY", default="")

# Sender.net API — marketing emails (campaigns, offers, newsletters)
SENDER_NET_API_KEY = env("SENDER_NET_API_KEY", default="")
SENDER_NET_FROM_EMAIL = env("SENDER_NET_FROM_EMAIL", default="")
SENDER_NET_FROM_NAME = env("SENDER_NET_FROM_NAME", default="")

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
