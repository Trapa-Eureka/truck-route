"""API errors: one JSON shape for every failure (docs/api-contract.md, "Errors").

    {"error": {"code": "GEOCODE_NOT_FOUND", "message": "...", "field": "origin"}}

Domain code raises ordinary exceptions (``InvalidInput``, ``GeocodeNotFound``,
``ForecastOutOfRange`` ...). ``api_exception_handler`` turns them into this shape, so the logic
modules know nothing about HTTP.
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .tomtom import GeocodeNotFound, NoRoute, RoutingUnavailable
from .weather import ForecastOutOfRange, WeatherUnavailable

logger = logging.getLogger(__name__)


class InvalidInput(Exception):
    """The request is malformed or not allowed. ``field`` names the offending field."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class DepartureInPast(Exception):
    """The departure time has already passed."""


def _body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    error = {"code": code, "message": message}
    error.update({key: value for key, value in extra.items() if value is not None})
    return {"error": error}


def _forecast_message(exc: ForecastOutOfRange) -> tuple[str, str | None]:
    if exc.forecast_end is None:
        return "The weather forecast does not reach the time this trip needs.", None
    end = exc.forecast_end.astimezone(timezone.utc)
    return (
        "The weather forecast does not reach the time this trip needs. "
        f"It is available until {end:%b %d, %H:%M} UTC.",
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def to_api_error(exc: Exception) -> tuple[int, dict[str, Any]] | None:
    """The (HTTP status, body) for a domain exception, or ``None`` if it is not one."""
    if isinstance(exc, InvalidInput):
        return 400, _body("INVALID_INPUT", exc.message, field=exc.field)
    if isinstance(exc, DepartureInPast):
        return 400, _body("DEPARTURE_IN_PAST", "The departure time is in the past.", field="departure")
    if isinstance(exc, GeocodeNotFound):
        message = f'Could not find "{exc.query}". Try adding a city and state.'
        return 422, _body("GEOCODE_NOT_FOUND", message, field=exc.field)
    if isinstance(exc, NoRoute):
        return 422, _body("NO_ROUTE", "No truck route was found between these places.")
    if isinstance(exc, ForecastOutOfRange):
        message, forecast_end = _forecast_message(exc)
        return 422, _body("FORECAST_OUT_OF_RANGE", message, forecast_end=forecast_end)
    if isinstance(exc, RoutingUnavailable):
        logger.warning("routing unavailable: %s", exc)
        return 502, _body("ROUTING_UNAVAILABLE", "The routing service is not available right now. Please try again.")
    if isinstance(exc, WeatherUnavailable):
        logger.warning("weather unavailable: %s", exc)
        return 502, _body("WEATHER_UNAVAILABLE", "The weather service is not available right now. Please try again.")
    return None


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler: domain errors and DRF's own errors, all in the contract shape."""
    mapped = to_api_error(exc)
    if mapped is not None:
        status, body = mapped
        return Response(body, status=status)

    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, APIException):
        # Unreadable JSON, wrong method or media type: all "the request is not acceptable".
        response.data = _body("INVALID_INPUT", str(exc.detail))
    return response
