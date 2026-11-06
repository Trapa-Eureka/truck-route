"""TomTom geocoding and truck routing (CLAUDE.md section 7).

Measured facts this module relies on (2026-11-06):

* Routing: ``travelMode=truck`` with ``maxAlternatives=2`` returned 3 routes on every trip tried,
  but TomTom only promises "up to N", so fewer routes are passed on as they are. The first
  route is TomTom's own preferred one; its order is kept.
* A route is ``legs[].points[]`` (latitude and longitude only) plus ``guidance.instructions[]``
  whose ``pointIndex`` / ``routeOffsetInMeters`` / ``travelTimeInSeconds`` become the anchors that
  time is interpolated between (``sampling.py``).
* No route: HTTP 400 with ``detailedError.code`` ``NO_ROUTE_FOUND`` or ``MAP_MATCHING_FAILURE``
  (an end point that is not near a road). A past ``departAt`` is accepted without error, so the
  caller must reject it. Origin = destination gives a route of length 0.
* Geocoding: ``countrySet=US``, ``limit=1``; an unknown address is HTTP 200 with no results.

Error messages never contain the request URL, which carries the API key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import quote

import requests

from .http import get_json
from .sampling import Anchor

BASE_URL = "https://api.tomtom.com"
KG_PER_LB = 0.45359237
REQUEST_TIMEOUT_SECONDS = 40  # a 3-route cross-country answer takes 6 to 10 seconds
ROUTE_CACHE_SECONDS = 15 * 60
GEOCODE_CACHE_SECONDS = 24 * 60 * 60
MAX_ROUTES = 3
_NO_ROUTE_CODES = {"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"}


class TomTomError(Exception):
    """Base class for TomTom failures."""


class GeocodeNotFound(TomTomError):
    """The address matched nothing. ``field`` is set by the caller (origin or destination)."""

    def __init__(self, query: str, field: str | None = None) -> None:
        super().__init__(f"Could not find {query!r}.")
        self.query = query
        self.field = field


class NoRoute(TomTomError):
    """TomTom found no truck route between the two places."""


class RoutingUnavailable(TomTomError):
    """TomTom failed, timed out, refused the key, or sent data we cannot read."""


@dataclass(frozen=True)
class Place:
    query: str
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RawRoute:
    """A route as TomTom describes it, before any weather is involved."""

    #: ``(lat, lon)`` along the whole route.
    points: tuple[tuple[float, float], ...]
    anchors: tuple[Anchor, ...]
    length_m: float
    time_s: float


class _Cache(Protocol):
    def get(self, key: str, default: Any = ...) -> Any: ...

    def set(self, key: str, value: Any, timeout: int | None = ...) -> Any: ...


def _format_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_route(raw: dict[str, Any]) -> RawRoute:
    points: list[tuple[float, float]] = []
    for leg in raw["legs"]:
        leg_points = [(float(p["latitude"]), float(p["longitude"])) for p in leg["points"]]
        # Consecutive legs share their joining point.
        if points and leg_points and points[-1] == leg_points[0]:
            leg_points = leg_points[1:]
        points.extend(leg_points)

    instructions = (raw.get("guidance") or {}).get("instructions") or []
    anchors = tuple(
        Anchor(
            point_index=int(i["pointIndex"]),
            offset_m=float(i["routeOffsetInMeters"]),
            time_s=float(i["travelTimeInSeconds"]),
        )
        for i in instructions
    )
    summary = raw["summary"]
    return RawRoute(
        points=tuple(points),
        anchors=anchors,
        length_m=float(summary["lengthInMeters"]),
        time_s=float(summary["travelTimeInSeconds"]),
    )


class TomTomClient:
    """Geocodes addresses and fetches truck routes. Both answers are cached."""

    def __init__(
        self,
        api_key: str,
        session: Any = None,
        cache: _Cache | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("a TomTom API key is required")
        if cache is None:
            from django.core.cache import cache as django_cache

            cache = django_cache
        self._key = api_key
        self._session = session if session is not None else requests.Session()
        self._cache = cache
        self._sleep = sleep

    def _get(self, url: str, params: dict[str, Any]) -> tuple[int, Any]:
        return get_json(
            self._session,
            url,
            {**params, "key": self._key},
            service="TomTom",
            error=RoutingUnavailable,
            timeout=REQUEST_TIMEOUT_SECONDS,
            sleep=self._sleep,
        )

    # --------------------------------------------------------------------------- geocoding

    def geocode(self, query: str) -> Place:
        """The first US match for ``query``. Raises ``GeocodeNotFound`` if there is none."""
        cache_key = f"tomtom:geocode:{query.strip().lower()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{BASE_URL}/search/2/geocode/{quote(query.strip(), safe='')}.json"
        status, body = self._get(url, {"countrySet": "US", "limit": 1})
        if status != 200:
            raise RoutingUnavailable(f"TomTom rejected the address lookup (HTTP {status}).")
        try:
            results = body["results"]
            if not isinstance(results, list):
                raise TypeError("results is not a list")
            if not results:
                raise GeocodeNotFound(query)
            first = results[0]
            place = Place(
                query=query,
                label=first.get("address", {}).get("freeformAddress") or query.strip(),
                lat=float(first["position"]["lat"]),
                lon=float(first["position"]["lon"]),
            )
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise RoutingUnavailable("TomTom sent an address answer that cannot be read.") from None

        self._cache.set(cache_key, place, GEOCODE_CACHE_SECONDS)
        return place

    # ---------------------------------------------------------------------------- routing

    def routes(
        self, origin: Place, destination: Place, departure: datetime, load_weight_lb: float
    ) -> list[RawRoute]:
        """Up to 3 truck routes, in TomTom's order. Raises ``NoRoute`` if there is none."""
        weight_kg = round(load_weight_lb * KG_PER_LB)
        depart_at = _format_utc(departure)
        cache_key = (
            f"tomtom:route:{origin.lat:.5f},{origin.lon:.5f}:"
            f"{destination.lat:.5f},{destination.lon:.5f}:{depart_at}:{weight_kg}"
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        url = (
            f"{BASE_URL}/routing/1/calculateRoute/"
            f"{origin.lat:.6f},{origin.lon:.6f}:{destination.lat:.6f},{destination.lon:.6f}/json"
        )
        status, body = self._get(
            url,
            {
                "travelMode": "truck",
                "vehicleCommercial": "true",
                "vehicleWeight": weight_kg,
                "maxAlternatives": MAX_ROUTES - 1,
                "departAt": depart_at,
                "instructionsType": "coded",
            },
        )
        if status == 400:
            detail = body.get("detailedError") if isinstance(body, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else None
            if code in _NO_ROUTE_CODES:
                raise NoRoute("TomTom found no truck route between these places.")
            raise RoutingUnavailable(f"TomTom rejected the route request ({code or 'HTTP 400'}).")

        try:
            routes = [_parse_route(raw) for raw in body["routes"][:MAX_ROUTES]]
        except (KeyError, TypeError, ValueError, AttributeError):
            raise RoutingUnavailable("TomTom sent a route answer that cannot be read.") from None
        if not routes:
            raise NoRoute("TomTom found no truck route between these places.")

        self._cache.set(cache_key, routes, ROUTE_CACHE_SECONDS)
        return routes
