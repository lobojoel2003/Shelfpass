"""Django settings for Shelfpass.

Every deployment-specific value comes from environment variables so the same
image runs in development, CI and production. See ``.env.example`` for the
full list.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc


# ----------------------------------------------------------------- core ---

DEBUG = env_bool("SHELFPASS_DEBUG", default=False)

SECRET_KEY = os.environ.get("SHELFPASS_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or env_bool("SHELFPASS_ALLOW_INSECURE_KEY"):
        SECRET_KEY = "insecure-development-key-do-not-use-in-production"  # noqa: S105
    else:
        raise ImproperlyConfigured(
            "SHELFPASS_SECRET_KEY is not set. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(50))'`."
        )

# localhost is always allowed so container health checks work behind any domain.
ALLOWED_HOSTS = [
    *env_list("SHELFPASS_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]"),
    "localhost",
    "127.0.0.1",
]
CSRF_TRUSTED_ORIGINS = env_list("SHELFPASS_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "shelfpass.core",
    "shelfpass.orgs",
    "shelfpass.facilities",
    "shelfpass.inventory",
    "shelfpass.correspondence",
    "shelfpass.shipping",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "shelfpass.orgs.middleware.CurrentOrganizationMiddleware",
]

ROOT_URLCONF = "shelfpass.urls"
WSGI_APPLICATION = "shelfpass.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PACKAGE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shelfpass.core.context_processors.shelfpass",
            ],
        },
    },
]

# ------------------------------------------------------------- database ---

# An empty DATABASE_URL (as in .env.example) means "use the local SQLite file".
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=env_int("SHELFPASS_DB_CONN_MAX_AGE", 60),
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------- auth/i18n ---

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("SHELFPASS_TIME_ZONE", "America/New_York")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------- static ---

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("SHELFPASS_STATIC_ROOT", BASE_DIR / "staticfiles"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG or env_bool("SHELFPASS_SIMPLE_STATIC")
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# ------------------------------------------------------------- security ---

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = env_int("SHELFPASS_SESSION_AGE", 60 * 60 * 12)
CSRF_COOKIE_HTTPONLY = False  # the intake form's fetch() calls read it
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if env_bool("SHELFPASS_BEHIND_PROXY"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if env_bool("SHELFPASS_HTTPS", default=not DEBUG):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SHELFPASS_SSL_REDIRECT", default=False)
    SECURE_HSTS_SECONDS = env_int("SHELFPASS_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = env_bool("SHELFPASS_HSTS_PRELOAD", default=False)
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

# ---------------------------------------------------------------- cache ---

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "shelfpass",
    }
}

# -------------------------------------------------------------- logging ---

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("SHELFPASS_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}

# ------------------------------------------------------ shelfpass itself ---

SHELFPASS = {
    # Directory holding the facility-rules dataset (``dataset/`` in the repo).
    "DATASET_DIR": Path(os.environ.get("SHELFPASS_DATASET_DIR", BASE_DIR / "dataset")),
    # Where volunteers send corrections to the shared dataset.
    "DATASET_REPO_URL": os.environ.get(
        "SHELFPASS_DATASET_REPO_URL", "https://github.com/lobojoel2003/Shelfpass"
    ),
    # Facility pages and the anonymised rejection dataset are readable without
    # logging in. Person data is never public.
    "PUBLIC_DATA": env_bool("SHELFPASS_PUBLIC_DATA", default=True),
    # Open Library book lookup.
    "OPENLIBRARY_ENABLED": env_bool("SHELFPASS_OPENLIBRARY_ENABLED", default=True),
    "OPENLIBRARY_BASE_URL": os.environ.get(
        "SHELFPASS_OPENLIBRARY_BASE_URL", "https://openlibrary.org"
    ),
    "OPENLIBRARY_TIMEOUT": float(os.environ.get("SHELFPASS_OPENLIBRARY_TIMEOUT", "6")),
    "OPENLIBRARY_USER_AGENT": os.environ.get(
        "SHELFPASS_OPENLIBRARY_USER_AGENT",
        "Shelfpass/1.0 (+https://github.com/lobojoel2003/Shelfpass)",
    ),
    # Rejection-history window shown on facility pages and during intake.
    "REJECTION_WINDOW_DAYS": env_int("SHELFPASS_REJECTION_WINDOW_DAYS", 365),
}
