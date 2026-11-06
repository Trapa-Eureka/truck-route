"""Django settings for the Spotter weather-aware truck routing API.

Secrets and per-environment values come from environment variables
(the repo-root ``.env`` is loaded for local development).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = _env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is not set (see .env.example).")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# External APIs. The TomTom key is server-side only; never expose it to the browser.
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")

INSTALLED_APPS = [
    "rest_framework",
    "trip",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # A long trip answers with about 800 KB of JSON (1,000 checkpoints); gzip makes it a fraction.
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# The API is stateless: no models, no users, no sessions.
DATABASES: dict = {}

# Weather responses are cached here (see CLAUDE.md section 7). LocMem keeps only 300 entries by
# default; one 10-mile analysis alone caches about 350 locations x several hours.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "spotter-default",
        "OPTIONS": {"MAX_ENTRIES": 50_000},
    },
    # Request counters (trip/throttling.py), apart from the weather entries that could evict them.
    "throttle": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "spotter-throttle",
        "OPTIONS": {"MAX_ENTRIES": 20_000},
    },
}

# Requests allowed per client address (trip/throttling.py). One analysis on screen is two "trip"
# requests (routes, then the heatmap), so these allow 6 analyses a minute and 60 a day; typing
# in a From / To field is at most 4 "places" requests a second and usually far fewer.
RATE_LIMITS = {
    "trip_minute": "12/min",
    "trip_day": "120/day",
    "places_minute": "90/min",
    "places_day": "1500/day",
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    # Every error, ours and DRF's, has the shape in docs/api-contract.md.
    "EXCEPTION_HANDLER": "trip.errors.api_exception_handler",
    # JSON only: "?format=xml" is an ordinary unknown parameter, not a 404.
    "URL_FORMAT_OVERRIDE": None,
    # How many proxies sit in front of the app. The request limits count per client address, and
    # behind a proxy that address is in X-Forwarded-For; without this number a client could
    # choose its own. Unset (local development) means the connecting address is used.
    "NUM_PROXIES": int(os.environ["DJANGO_NUM_PROXIES"]) if os.environ.get("DJANGO_NUM_PROXIES") else None,
}

# Errors go to the console with their traceback, with DEBUG off too (the host collects stdout).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "trip": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

LANGUAGE_CODE = "en-us"
# All times are handled in UTC; the frontend formats them for display.
TIME_ZONE = "UTC"
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
