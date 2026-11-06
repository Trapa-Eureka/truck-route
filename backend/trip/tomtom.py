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
* Places: Fuzzy Search (``/search/2/search``) finds addresses, cities **and named places** (a
  building, a station), which the plain Geocoding API does not: "Willis Tower, Chicago" is a
  neighbourhood there but the tower in Fuzzy Search. Typing a text (``suggest``) uses
  ``typeahead=true``; confirming a typed text (``geocode``) takes the first result. An unknown
  text is HTTP 200 with no results.
* Reverse geocoding (``/search/2/reverseGeocode``) turns the browser's position into an address;
  its ``countryCode`` tells a position outside the US, which this app does not route.

Error messages never contain the request URL, which carries the API key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import quote

import requests

from .http import get_json
from .sampling import Anchor, check_route

BASE_URL = "https://api.tomtom.com"
KG_PER_LB = 0.45359237
REQUEST_TIMEOUT_SECONDS = 40  # a 3-route cross-country answer takes 6 to 10 seconds
ROUTE_CACHE_SECONDS = 15 * 60
GEOCODE_CACHE_SECONDS = 24 * 60 * 60
SUGGEST_CACHE_SECONDS = 60 * 60
MIN_SUGGEST_CHARS = 3
MAX_SUGGESTIONS = 5
#: Ask for more than are shown: the same place often comes back several times.
_SUGGEST_FETCH = 10
REVERSE_RADIUS_M = 1000
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


class LocationNotCovered(TomTomError):
    """A position is outside the United States, or has no address nearby."""


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
class Suggestion:
    """One choice in the From / To list."""

    id: str
    #: ``place`` (a building, station ...), ``address`` or ``area`` (a city, a neighbourhood).
    kind: str
    #: The main line in the list ("Willis Tower", "233 South Wacker Drive").
    name: str
    #: The line under it ("233 South Wacker Drive, Chicago, IL 60606", "Chicago, IL 60606").
    detail: str
    #: The whole text put in the input when chosen.
    label: str
    lat: float
    lon: float


def _describe(result: dict[str, Any]) -> tuple[str, str, str, str]:
    """``(kind, name, detail, label)`` of a search result."""
    address = result.get("address") or {}
    freeform = (address.get("freeformAddress") or "").strip()
    poi_name = ((result.get("poi") or {}).get("name") or "").strip()
    if poi_name:
        label = f"{poi_name}, {freeform}" if freeform else poi_name
        return "place", poi_name, freeform, label
    head, _, tail = freeform.partition(", ")
    kind = "area" if result.get("type") == "Geography" else "address"
    return kind, head or freeform, tail, freeform


def _position(result: dict[str, Any]) -> tuple[float, float]:
    position = result["position"]
    return float(position["lat"]), float(position["lon"])


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
        """The first US match for a typed ``query``. Raises ``GeocodeNotFound`` if there is none."""
        cache_key = f"tomtom:geocode:{query.strip().lower()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            # The key ignores case, so the cached place may carry another spelling of the query.
            return replace(cached, query=query)

        url = f"{BASE_URL}/search/2/search/{quote(query.strip(), safe='')}.json"
        status, body = self._get(url, {"countrySet": "US", "limit": 1})
        if status != 200:
            # HTTP 400 is TomTom's answer to a text it cannot search for ("%%%"): the text is the
            # problem, not the service, so say "not found" and do not invite a retry.
            raise GeocodeNotFound(query)
        try:
            results = body["results"]
            if not isinstance(results, list):
                raise TypeError("results is not a list")
            if not results:
                raise GeocodeNotFound(query)
            first = results[0]
            lat, lon = _position(first)
            place = Place(
                query=query,
                label=_describe(first)[3] or query.strip(),
                lat=lat,
                lon=lon,
            )
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise RoutingUnavailable("TomTom sent an address answer that cannot be read.") from None

        self._cache.set(cache_key, place, GEOCODE_CACHE_SECONDS)
        return place

    def suggest(self, query: str) -> list[Suggestion]:
        """Up to 5 choices for what is being typed: places, addresses and cities in the US."""
        text = " ".join(query.split())
        if len(text) < MIN_SUGGEST_CHARS:
            return []
        cache_key = f"tomtom:suggest:{text.lower()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return list(cached)

        url = f"{BASE_URL}/search/2/search/{quote(text, safe='')}.json"
        status, body = self._get(url, {"countrySet": "US", "limit": _SUGGEST_FETCH, "typeahead": "true"})
        if status != 200:
            return []  # HTTP 400: a text TomTom cannot search for has no matches
        try:
            results = body["results"]
            if not isinstance(results, list):
                raise TypeError("results is not a list")
            suggestions: list[Suggestion] = []
            seen: set[tuple[str, str]] = set()
            for result in results:
                try:
                    lat, lon = _position(result)
                    kind, name, detail, label = _describe(result)
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue  # one unreadable result does not spoil the list
                if not label:
                    continue
                # The same place is often listed several times a few meters apart.
                identity = (name.lower(), detail.lower())
                if identity in seen:
                    continue
                seen.add(identity)
                suggestions.append(
                    Suggestion(
                        id=str(result.get("id") or f"{lat:.5f},{lon:.5f}"),
                        kind=kind,
                        name=name,
                        detail=detail,
                        label=label,
                        lat=lat,
                        lon=lon,
                    )
                )
                if len(suggestions) == MAX_SUGGESTIONS:
                    break
        except (KeyError, TypeError):
            raise RoutingUnavailable("TomTom sent a place answer that cannot be read.") from None

        self._cache.set(cache_key, tuple(suggestions), SUGGEST_CACHE_SECONDS)
        return suggestions

    def reverse(self, lat: float, lon: float) -> Place:
        """The address at a position (the browser's location). Raises ``LocationNotCovered``."""
        cache_key = f"tomtom:reverse:{lat:.4f},{lon:.4f}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{BASE_URL}/search/2/reverseGeocode/{lat:.6f},{lon:.6f}.json"
        status, body = self._get(url, {"radius": REVERSE_RADIUS_M})
        if status != 200:
            raise RoutingUnavailable(f"TomTom rejected the location lookup (HTTP {status}).")
        try:
            addresses = body["addresses"]
            if not isinstance(addresses, list):
                raise TypeError("addresses is not a list")
            if not addresses:
                raise LocationNotCovered("no address near this position")
            address = addresses[0]["address"]
            country = address.get("countryCode")
            label = (address.get("freeformAddress") or "").strip()
        except (KeyError, TypeError, IndexError, AttributeError):
            raise RoutingUnavailable("TomTom sent a location answer that cannot be read.") from None
        if country != "US":
            raise LocationNotCovered(f"position is in {country or 'an unknown country'}")
        if not label:
            raise LocationNotCovered("no address near this position")

        place = Place(query=f"{lat:.5f},{lon:.5f}", label=label, lat=round(lat, 5), lon=round(lon, 5))
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
        # Refuse a route that checkpoints cannot be built from (guidance that goes backwards in
        # time, a point index past the line ...) before it is cached: cached, it would fail every
        # request for this trip for 15 minutes. A route of length 0 is left for the caller, which
        # reports it as "the same place".
        for route in routes:
            if route.length_m > 0:
                try:
                    check_route(route.points, route.anchors, route.length_m, route.time_s)
                except ValueError:
                    raise RoutingUnavailable("TomTom sent a route that is not consistent.") from None

        self._cache.set(cache_key, routes, ROUTE_CACHE_SECONDS)
        return routes
