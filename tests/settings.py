"""Settings used by the test suite."""

import os

os.environ.setdefault("SHELFPASS_ALLOW_INSECURE_KEY", "1")
os.environ.setdefault("SHELFPASS_HTTPS", "0")

from shelfpass.settings import *  # noqa: F403
from shelfpass.settings import SHELFPASS, STORAGES

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
SHELFPASS = {**SHELFPASS, "OPENLIBRARY_ENABLED": True, "OPENLIBRARY_TIMEOUT": 0.5}
WHITENOISE_AUTOREFRESH = True  # no collectstatic in tests
