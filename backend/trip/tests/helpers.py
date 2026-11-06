"""Fake services and a real recorded route for the analysis and view tests."""

from __future__ import annotations

import json
from pathlib import Path

from trip.sampling import Anchor
from trip.tomtom import GeocodeNotFound, Place, RawRoute
from trip.weather import WeatherSample

FIXTURE = Path(__file__).parent / "fixtures" / "tomtom_route_prefix.json"

CHICAGO = Place("Chicago, IL", "Chicago, IL", 41.883229, -87.632398)
MADISON = Place("Madison, WI", "Madison, WI", 43.074761, -89.383761)


def recorded_route(time_factor: float = 1.0, length_factor: float = 1.0) -> RawRoute:
    """The first 156.6 miles of a real TomTom Chicago route, optionally slower / longer.

    Scaling the times and offsets gives a believable second and third route over the same line.
    """
    data = json.loads(FIXTURE.read_text())
    return RawRoute(
        points=tuple(tuple(p) for p in data["points"]),
        anchors=tuple(
            Anchor(i, offset * length_factor, seconds * time_factor)
            for i, offset, seconds in data["anchors"]
        ),
        length_m=data["total_length_m"] * length_factor,
        time_s=data["total_time_s"] * time_factor,
    )


class FakeRouting:
    """Geocodes from a dict and returns fixed routes. Records what it was asked."""

    def __init__(self, routes, places=None):
        self._routes = routes
        self._places = places if places is not None else {"Chicago, IL": CHICAGO, "Madison, WI": MADISON}
        self.geocoded = []
        self.route_calls = []

    def geocode(self, query):
        self.geocoded.append(query)
        if query not in self._places:
            raise GeocodeNotFound(query)
        return self._places[query]

    def routes(self, origin, destination, departure, load_weight_lb):
        self.route_calls.append((origin, destination, departure, load_weight_lb))
        return self._routes


class FakeWeather:
    """Answers every query with ``fn(query)``; records each call's queries."""

    def __init__(self, fn=None):
        self._fn = fn or (lambda query: WeatherSample(5.0, 0.0, 0.0))
        self.calls = []

    def get_weather_at(self, queries):
        self.calls.append(list(queries))
        return [self._fn(q) for q in queries]


def calm(query=None):
    return WeatherSample(5.0, 0.0, 0.0)
