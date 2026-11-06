"""Validation of the analyze request body (docs/api-contract.md, "Request body")."""

from __future__ import annotations

import math
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
class AnalyzeRequest:
    origin: str
    destination: str
    departure: datetime  # timezone-aware, UTC
    load_weight_lb: float
    interval_miles: int


def _address(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f"Enter the {field}.", field)
    value = value.strip()
    if len(value) > MAX_ADDRESS_LENGTH:
        raise InvalidInput(f"The {field} is too long (at most {MAX_ADDRESS_LENGTH} characters).", field)
    return value


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
    departure = departure.astimezone(timezone.utc)
    if departure >= LATEST_DEPARTURE:
        raise InvalidInput("The departure is too far in the future.", "departure")
    if departure < now - PAST_GRACE:
        raise DepartureInPast()
    return departure


def _load_weight(data: dict[str, Any]) -> float:
    value = data.get("load_weight_lb")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
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
