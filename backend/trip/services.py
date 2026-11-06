"""The shared external-service clients (one HTTP session each, the default Django cache)."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .tomtom import TomTomClient
from .weather_client import WeatherClient, get_client

_tomtom: TomTomClient | None = None


def get_tomtom() -> TomTomClient:
    global _tomtom
    if _tomtom is None:
        if not settings.TOMTOM_API_KEY:
            raise ImproperlyConfigured("TOMTOM_API_KEY is not set (see .env.example).")
        _tomtom = TomTomClient(settings.TOMTOM_API_KEY)
    return _tomtom


def get_weather() -> WeatherClient:
    return get_client()
