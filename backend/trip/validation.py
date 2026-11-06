"""Validation of the analyze request body (docs/api-contract.md, "Request body")."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import DepartureInPast, InvalidInput

ALLOWED_INTERVALS = (10, 25, 50)
MAX_ADDRESS_LENGTH = 200
MAX_LOAD_WEIGHT_LB = 1_000_000
#: A departure picked as "now" in a form is a few seconds old by the time it arrives.
PAST_GRACE = timedelta(minutes=5)
#: Far beyond any forecast; only keeps date arithmetic from overflowing.
LATEST_DEPARTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class PickedPlace:
    """A place the user chose from the list (or "my location"): no address lookup is needed."""

    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class AnalyzeRequest:
    origin: str | PickedPlace
    destination: str | PickedPlace
    departure: datetime  # timezone-aware, UTC
    load_weight_lb: float
    interval_miles: int


#: A box around the 50 states: Hawaii in the south, northern Alaska in the north, the Aleutians
#: up to the date line in the west, Maine in the east. Routes are US only (typed text is searched
#: with ``countrySet=US``); a chosen place carries its own position, so it is checked here. The
#: box is coarse on purpose: it stops a position on another continent without a lookup.
US_LATITUDE = (18.0, 72.0)
US_LONGITUDE = (-180.0, -66.0)


def _is_finite_number(value: Any) -> bool:
    """A real, finite number. JSON allows integers too large for a float (10**400)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_plain_text(value: str) -> bool:
    """No control characters (NUL, escape ...) and no lone surrogates, which cannot be sent on."""
    return not any(unicodedata.category(ch) in ("Cc", "Cs") for ch in value)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f"Enter the {field}.", field)
    value = " ".join(value.split())  # also turns a pasted line break or tab into a space
    if not _is_plain_text(value):
        raise InvalidInput(f"The {field} contains characters that cannot be used.", field)
    if len(value) > MAX_ADDRESS_LENGTH:
        raise InvalidInput(f"The {field} is too long (at most {MAX_ADDRESS_LENGTH} characters).", field)
    return value


def _coordinate(value: Any, name: str, limit: float, field: str | None) -> float:
    if not _is_finite_number(value):
        raise InvalidInput(f"The {name} must be a number.", field)
    if abs(value) > limit:
        raise InvalidInput(f"The {name} must be between -{limit:g} and {limit:g}.", field)
    return float(value)


def _in_the_us(lat: float, lon: float) -> bool:
    return US_LATITUDE[0] <= lat <= US_LATITUDE[1] and US_LONGITUDE[0] <= lon <= US_LONGITUDE[1]


def _address(data: dict[str, Any], field: str) -> str | PickedPlace:
    """Typed text, or a chosen place ``{"label", "lat", "lon"}``."""
    value = data.get(field)
    if isinstance(value, dict):
        place = PickedPlace(
            label=_text(value.get("label"), field),
            lat=_coordinate(value.get("lat"), "latitude", 90, field),
            lon=_coordinate(value.get("lon"), "longitude", 180, field),
        )
        if not _in_the_us(place.lat, place.lon):
            raise InvalidInput(f"The {field} is outside the United States. Routes are available in the US only.", field)
        return place
    return _text(value, field)


def parse_place_query(params: Any) -> str:
    """The ``q`` of ``GET /api/places``."""
    value = params.get("q")
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput("Give the text to search for in q.")
    value = " ".join(value.split())
    if not _is_plain_text(value):
        raise InvalidInput("The search text contains characters that cannot be used.")
    if len(value) > MAX_ADDRESS_LENGTH:
        raise InvalidInput(f"The search text is too long (at most {MAX_ADDRESS_LENGTH} characters).")
    return value


def parse_position(params: Any) -> tuple[float, float]:
    """The ``lat`` and ``lon`` of ``GET /api/places/reverse``."""
    numbers = []
    for name, limit in (("lat", 90), ("lon", 180)):
        raw = params.get(name)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise InvalidInput(f"Give {name} as a number.") from None
        numbers.append(_coordinate(number, name, limit, None))
    return numbers[0], numbers[1]


def _departure(data: dict[str, Any], now: datetime) -> datetime:
    value = data.get("departure")
    if not isinstance(value, str):
        raise InvalidInput("Enter the departure date and time.", "departure")
    try:
        departure = datetime.fromisoformat(value.strip())
    except ValueError:
        raise InvalidInput("The departure is not a valid date and time (ISO 8601).", "departure") from None
    if departure.tzinfo is None or departure.utcoffset() is None:
        raise InvalidInput("The departure needs a time zone, for example 2026-11-09T14:00:00Z.", "departure")
    try:
        departure = departure.astimezone(timezone.utc)
    except OverflowError:  # year 1 or 9999 with an offset that leaves the calendar
        raise InvalidInput("The departure is not a valid date and time (ISO 8601).", "departure") from None
    if departure >= LATEST_DEPARTURE:
        raise InvalidInput("The departure is too far in the future.", "departure")
    if departure < now - PAST_GRACE:
        raise DepartureInPast()
    return departure


def _load_weight(data: dict[str, Any]) -> float:
    value = data.get("load_weight_lb")
    if not _is_finite_number(value):
        raise InvalidInput("Enter the load weight in pounds.", "load_weight_lb")
    if value < 0:
        raise InvalidInput("The load weight cannot be negative.", "load_weight_lb")
    if value > MAX_LOAD_WEIGHT_LB:
        raise InvalidInput(f"The load weight is too large (at most {MAX_LOAD_WEIGHT_LB:,} lb).", "load_weight_lb")
    return float(value)


def _interval(data: dict[str, Any]) -> int:
    value = data.get("interval_miles")
    allowed = isinstance(value, (int, float)) and not isinstance(value, bool) and value in ALLOWED_INTERVALS
    if not allowed:
        raise InvalidInput("The sampling interval must be 10, 25 or 50 miles.", "interval_miles")
    return int(value)


def parse_analyze_request(data: Any, now: datetime) -> AnalyzeRequest:
    """Check the request body. Raises ``InvalidInput`` or ``DepartureInPast``.

    ``now`` is passed in (timezone-aware) so the logic never reads the clock itself.
    """
    if not isinstance(data, dict):
        raise InvalidInput("The request body must be a JSON object.")
    return AnalyzeRequest(
        origin=_address(data, "origin"),
        destination=_address(data, "destination"),
        departure=_departure(data, now),
        load_weight_lb=_load_weight(data),
        interval_miles=_interval(data),
    )
