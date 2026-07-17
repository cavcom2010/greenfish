"""
Home-server settings: local settings + hashed static filenames.

Used by deploy/home/start.sh (gunicorn + nginx). Static files carry a
content hash in the filename so browsers can cache them for 7 days
(nginx /static/ max-age) without ever serving a stale asset after a
deploy — unversioned URLs previously left phones running week-old
CSS/JS. Requires collectstatic, which start.sh runs on every start.

Not for `manage.py runserver` — the dev static server can't resolve
hashed names; keep using config.settings.local for development.
"""
from .local import *

# Hashed URLs are disabled while DEBUG is on (HashedFilesMixin.url), and the
# home server is LAN-facing anyway — no debug error pages for guests.
DEBUG = False

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
