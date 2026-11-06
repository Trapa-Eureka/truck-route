"""The analyze use case: geocode, route, weather at each ETA, risk, summary, recommendation.

This is where Steps 3 to 6 are put together. It takes its two external services (TomTom and the
weather client) as arguments, so the whole flow can be tested without a network.

Everything is computed at full precision. Rounding happens only when the response is built
(``_route_json``): coordinates to 5 decimals (about 1 m), miles to 2 decimals, times to the
second. The summary numbers that decide the recommendation are already the rounded values shown
on screen (``summary.py``).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from .errors import InvalidInput
from .geometry import Segment, joined, risk_segments
from .recommend import recommend
from .risk import CheckpointRisk, RiskLevel, assess_checkpoint
from .sampling import METERS_PER_MILE, Checkpoint, build_checkpoints, route_distances_m
from .summary import RouteSummary, Stretch, summarize_route
from .tomtom import GeocodeNotFound, Place, RawRoute
from .validation import AnalyzeRequest
from .weather import WeatherSample
from .weather_client import WeatherQuery

ROUTE_IDS = "ABC"


class RoutingService(Protocol):
    def geocode(self, query: str) -> Place: ...

    def routes(
        self, origin: Place, destination: Place, departure: datetime, load_weight_lb: float
    ) -> list[RawRoute]: ...


class WeatherService(Protocol):
    def get_weather_at(self, queries: Sequence[WeatherQuery]) -> list[WeatherSample]: ...


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coordinate(lon: float, lat: float) -> list[float]:
    return [round(lon, 5), round(lat, 5)]


def _geocode(routing: RoutingService, query: str, field: str) -> Place:
    try:
        return routing.geocode(query)
    except GeocodeNotFound as error:
        error.field = field
        raise


def _geocode_both(routing: RoutingService, request: AnalyzeRequest) -> tuple[Place, Place]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        origin = pool.submit(_geocode, routing, request.origin, "origin")
        destination = pool.submit(_geocode, routing, request.destination, "destination")
        return origin.result(), destination.result()


def _same_place(a: Place, b: Place) -> bool:
    return (round(a.lat, 5), round(a.lon, 5)) == (round(b.lat, 5), round(b.lon, 5))


def _place_json(place: Place) -> dict[str, Any]:
    return {"query": place.query, "label": place.label, "lat": place.lat, "lon": place.lon}


class _AnalyzedRoute:
    """One route with everything computed for it (full precision)."""

    def __init__(
        self,
        route_id: str,
        raw: RawRoute,
        checkpoints: list[Checkpoint],
        samples: list[WeatherSample],
        risks: list[CheckpointRisk],
        summary: RouteSummary,
        segments: list[Segment],
    ) -> None:
        self.id = route_id
        self.raw = raw
        self.checkpoints = checkpoints
        self.samples = samples
        self.risks = risks
        self.summary = summary
        self.segments = segments


def _checkpoint_json(cp: Checkpoint, sample: WeatherSample, risk: CheckpointRisk) -> dict[str, Any]:
    return {
        "index": cp.index,
        "mile": round(cp.mile, 2),
        "lat": round(cp.lat, 5),
        "lon": round(cp.lon, 5),
        "eta": _iso(cp.eta),
        "represents_miles": round(cp.represents_miles, 2),
        "weather": {
            "wind_mph": sample.wind_mph,
            "rain_in_hr": sample.rain_in_hr,
            "snow_in_hr": sample.snow_in_hr,
        },
        "level_by": {
            "wind": risk.level_by.wind.api_name,
            "rain": risk.level_by.rain.api_name,
            "snow": risk.level_by.snow.api_name,
        },
        "level": risk.level.api_name,
        "load_escalated": risk.load_escalated,
    }


def _summary_json(s: RouteSummary) -> dict[str, Any]:
    return {
        "distance_miles": s.distance_miles,
        "duration_minutes": s.duration_minutes,
        "arrival": _iso(s.arrival),
        "miles_by_level": {level.api_name: s.miles_by_level[level] for level in RiskLevel},
        "severe_miles": s.severe_miles,
        "high_miles": s.high_miles,
        "avg_risk": s.avg_risk,
        "has_no_travel": s.has_no_travel,
    }


def _route_json(route: _AnalyzedRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "summary": _summary_json(route.summary),
        "geometry": [_coordinate(lon, lat) for lon, lat in joined(route.segments)],
        "segments": [
            {
                "level": segment.level.api_name,
                "coordinates": [_coordinate(lon, lat) for lon, lat in segment.coordinates],
            }
            for segment in route.segments
        ],
        "checkpoints": [
            _checkpoint_json(cp, sample, risk)
            for cp, sample, risk in zip(route.checkpoints, route.samples, route.risks)
        ],
    }


def _stretch_ends_m(checkpoints: Sequence[Checkpoint]) -> list[float]:
    """Where each checkpoint's stretch ends, in meters from the origin."""
    ends, total = [], 0.0
    for cp in checkpoints:
        total += cp.represents_miles
        ends.append(total * METERS_PER_MILE)
    return ends


def resolve_trip(
    request: AnalyzeRequest, routing: RoutingService
) -> tuple[Place, Place, list[RawRoute]]:
    """Geocode both ends and fetch the routes. Shared by the analysis and the heatmap.

    The routes come from the routing client's cache when the same trip was asked for just
    before, so the second endpoint does not call TomTom again.
    """
    origin, destination = _geocode_both(routing, request)
    if _same_place(origin, destination):
        raise InvalidInput("The origin and the destination are the same place.", "destination")

    raw_routes = routing.routes(origin, destination, request.departure, request.load_weight_lb)
    if any(raw.length_m <= 0 for raw in raw_routes):
        raise InvalidInput("The origin and the destination are the same place.", "destination")
    return origin, destination, raw_routes


def analyze(
    request: AnalyzeRequest, routing: RoutingService, weather: WeatherService
) -> dict[str, Any]:
    """Run one analysis and return the ``POST /api/analyze`` response body.

    Raises the domain exceptions that ``errors.api_exception_handler`` turns into API errors.
    """
    origin, destination, raw_routes = resolve_trip(request, routing)

    checkpoints = [
        build_checkpoints(
            raw.points, raw.anchors, raw.length_m, raw.time_s, request.departure, request.interval_miles
        )
        for raw in raw_routes
    ]

    # One weather call for every checkpoint of every route: equal places are fetched once and
    # the requests are batched (weather_client.py).
    queries = [WeatherQuery(cp.lat, cp.lon, cp.eta) for cps in checkpoints for cp in cps]
    samples = weather.get_weather_at(queries)

    analyzed: list[_AnalyzedRoute] = []
    offset = 0
    for route_id, raw, cps in zip(ROUTE_IDS, raw_routes, checkpoints):
        route_samples = samples[offset : offset + len(cps)]
        offset += len(cps)
        risks = [
            assess_checkpoint(s.wind_mph, s.rain_in_hr, s.snow_in_hr, request.load_weight_lb)
            for s in route_samples
        ]
        summary = summarize_route(
            [Stretch(risk.level, cp.represents_miles) for cp, risk in zip(cps, risks)],
            raw.time_s,
            request.departure,
        )
        distances = route_distances_m(raw.points, raw.anchors, raw.length_m, raw.time_s)
        segments = risk_segments(
            raw.points, distances, _stretch_ends_m(cps), [risk.level for risk in risks]
        )
        analyzed.append(_AnalyzedRoute(route_id, raw, cps, route_samples, risks, summary, segments))

    recommendation = recommend({route.id: route.summary for route in analyzed})
    return {
        "origin": _place_json(origin),
        "destination": _place_json(destination),
        "routes": [_route_json(route) for route in analyzed],
        "recommendation": {
            "route_id": recommendation.route_id,
            "decided_by": recommendation.decided_by.value if recommendation.decided_by else None,
            "versus_route_id": recommendation.versus_route_id,
            "duration_delta_minutes": recommendation.duration_delta_minutes,
            "excluded_route_ids": list(recommendation.excluded_route_ids),
            "ranking": list(recommendation.ranking),
        },
    }
