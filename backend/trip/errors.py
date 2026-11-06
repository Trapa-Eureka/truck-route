"""API errors: one JSON shape for every failure (docs/api-contract.md, "Errors").

    {"error": {"code": "GEOCODE_NOT_FOUND", "message": "...", "field": "origin"}}

Domain code raises ordinary exceptions (``InvalidInput``, ``GeocodeNotFound``,
``ForecastOutOfRange`` ...). ``api_exception_handler`` turns them into this shape, so the logic
modules know nothing about HTTP.
"""

from __future__ import annotations

import logging
import math
from datetime import timezone
from typing import Any

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from rest_framework.exceptions import APIException, ParseError, Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .tomtom import GeocodeNotFound, LocationNotCovered, NoRoute, RoutingUnavailable
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
    if isinstance(exc, LocationNotCovered):
        message = "Your location is outside the United States or has no address nearby. Routes are available in the US only."
        return 422, _body("GEOCODE_NOT_FOUND", message)
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


def _framework_error(status: int, exc: Exception) -> dict[str, Any]:
    """The body for an error raised by the framework rather than by our own code."""
    if isinstance(exc, Throttled):
        wait = math.ceil(exc.wait) if exc.wait else None
        message = "Too many requests. Please wait a moment and try again."
        if wait:
            message = f"Too many requests. Please try again in {wait} seconds."
        return _body("RATE_LIMITED", message, retry_after_seconds=wait)
    if status == 404:
        return _body("NOT_FOUND", "There is nothing at this address.")
    if isinstance(exc, ParseError):
        # The parser's own text names Python internals; the client only needs to know this.
        return _body("INVALID_INPUT", "The request body is not valid JSON.")
    if isinstance(exc, APIException):
        # Wrong method or media type: "the request is not acceptable".
        return _body("INVALID_INPUT", str(exc.detail))
    return _body("INVALID_INPUT", "The request is not acceptable.")


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """DRF exception handler: every error leaves in the contract shape, never as an HTML page."""
    mapped = to_api_error(exc)
    if mapped is not None:
        status, body = mapped
        return Response(body, status=status)

    if isinstance(exc, RecursionError):  # a body of 100,000 nested brackets
        return Response(_body("INVALID_INPUT", "The request body is not valid JSON."), status=400)
    if isinstance(exc, RequestDataTooBig):
        return Response(_body("INVALID_INPUT", "The request body is too large."), status=400)

    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = _framework_error(response.status_code, exc)
        return response

    # Anything else is a bug or an input nobody foresaw. Log it with its traceback and still
    # answer in the contract shape: no HTML page, no debug page, nothing about the server.
    logger.exception("unhandled error in %s", context.get("view").__class__.__name__)
    return Response(_body("INTERNAL_ERROR", "Something went wrong on our side. Please try again."), status=500)


def _json(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse(_body(code, message), status=status)


def not_found(request: Any, exception: Exception | None = None) -> JsonResponse:
    """``handler404``: an address outside the API."""
    return _json(404, "NOT_FOUND", "There is nothing at this address.")


def bad_request(request: Any, exception: Exception | None = None) -> JsonResponse:
    """``handler400``: a request Django itself refuses (for example a wrong Host header)."""
    return _json(400, "INVALID_INPUT", "The request is not acceptable.")


def server_error(request: Any) -> JsonResponse:
    """``handler500``: an error outside the API views (they answer through the handler above)."""
    return _json(500, "INTERNAL_ERROR", "Something went wrong on our side. Please try again.")
