"""Tests for trip/heatmap.py: the 49-hour risk grid, with fake TomTom and weather."""

import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from trip.errors import InvalidInput
from trip.grid import corridor_grid
from trip.heatmap import HOURS, heatmap
from trip.tests.helpers import CHICAGO, FakeRouting, FakeWeather, calm, recorded_route
from trip.tomtom import GeocodeNotFound, NoRoute
from trip.validation import AnalyzeRequest
from trip.weather import ForecastOutOfRange, WeatherSample, WeatherUnavailable

UTC = timezone.utc
DEPART = datetime(2026, 11, 9, 12, 20, tzinfo=UTC)


def request(**override):
    base = dict(origin="Chicago, IL", destination="Madison, WI", departure=DEPART, load_weight_lb=42000.0, interval_miles=25)
    base.update(override)
    return AnalyzeRequest(**base)


def run(weather=None, routes=None, **req):
    routing = FakeRouting(routes if routes is not None else [recorded_route(), recorded_route(time_factor=1.2)])
    weather = weather or FakeWeather()
    return heatmap(request(**req), routing, weather), routing, weather


def levels(result):
    """The risk level of every point and hour: the whole part of the score."""
    return [[int(score) for score in row] for row in result["scores"]]


class TestShape:
    def test_keys_and_sizes(self):
        result, _, _ = run()
        assert set(result) == {"start", "hours", "spacing_deg", "points", "scores"}
        assert result["hours"] == HOURS == 49
        assert len(result["scores"]) == 49
        assert all(len(row) == len(result["points"]) for row in result["scores"])
        assert 10 < len(result["points"]) < 60  # a 157-mile route and its 40-mile margin

    def test_points_are_lon_lat_on_the_grid(self):
        result, _, _ = run()
        for lon, lat in result["points"]:
            assert lon % 0.5 == 0 and lat % 0.5 == 0
            assert -90 <= lat <= 90 and -180 <= lon <= 180
        assert 41.5 <= max(p[1] for p in result["points"]) and min(p[0] for p in result["points"]) < -89

    def test_points_match_the_corridor_grid_of_the_routes(self):
        result, _, _ = run()
        raws = [recorded_route(), recorded_route(time_factor=1.2)]
        expected, _ = corridor_grid([r.points for r in raws])
        assert result["points"] == [[lon, lat] for lat, lon in expected]

    def test_the_grid_spacing_is_reported(self):
        small, _, _ = run()
        assert small["spacing_deg"] == 0.5
        # a trip across the country with far-apart routes gets a coarser grid
        from trip.tomtom import RawRoute

        def line(points):
            return RawRoute(points=tuple(points), anchors=(), length_m=4_000_000.0, time_s=144_000.0)

        routes = [
            line([(47.6, -122.3), (45.0, -93.0), (42.4, -71.0)]),
            line([(37.8, -122.4), (38.0, -95.0), (37.0, -77.0)]),
            line([(32.7, -117.1), (32.0, -97.0), (30.3, -81.7)]),
        ]
        big, _, weather = run(routes=routes)
        assert big["spacing_deg"] > 0.5
        assert len(big["points"]) <= 600
        assert len(weather.calls[0]) == len(big["points"]) * 49

    def test_scores_are_numbers_from_0_to_4_with_two_decimals(self):
        result, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(40.0 + q.time.hour, 0.0, 0.0)))
        for row in result["scores"]:
            for score in row:
                assert 0.0 <= score <= 4.0
                assert score == round(score, 2)

    def test_the_result_is_plain_json(self):
        result, _, _ = run()
        assert json.loads(json.dumps(result, allow_nan=False)) == result


class TestHours:
    @pytest.mark.parametrize(
        "departure, start",
        [
            ("2026-11-09T12:00:00Z", "2026-11-09T12:00:00Z"),
            ("2026-11-09T12:29:59Z", "2026-11-09T12:00:00Z"),
            ("2026-11-09T12:30:00Z", "2026-11-09T13:00:00Z"),
            ("2026-11-09T12:59:00Z", "2026-11-09T13:00:00Z"),
            ("2026-11-09T23:40:00Z", "2026-11-10T00:00:00Z"),
        ],
    )
    def test_hour_zero_is_the_departure_rounded_to_the_nearest_hour(self, departure, start):
        result, _, _ = run(departure=datetime.fromisoformat(departure))
        assert result["start"] == start

    def test_start_is_utc_whatever_the_departure_offset(self):
        seoul = timezone(timedelta(hours=9))
        result, _, _ = run(departure=datetime(2026, 11, 9, 21, 20, tzinfo=seoul))
        assert result["start"] == "2026-11-09T12:00:00Z"

    def test_hour_zero_is_the_hour_a_checkpoint_at_departure_uses(self):
        # the origin checkpoint's ETA is the departure; its weather is for the nearest hour = start
        from trip.weather import nearest_hour

        for minute in (0, 20, 40):
            departure = DEPART.replace(minute=minute)
            result, _, _ = run(departure=departure)
            assert result["start"] == nearest_hour(departure).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_every_point_is_asked_for_every_hour_exactly_once(self):
        result, _, weather = run()
        assert len(weather.calls) == 1
        queries = weather.calls[0]
        n = len(result["points"])
        assert len(queries) == n * 49
        start = datetime(2026, 11, 9, 12, tzinfo=UTC)
        per_point = {}
        for q in queries:
            per_point.setdefault((q.lon, q.lat), []).append(q.time)
        assert len(per_point) == n
        for times in per_point.values():
            assert times == [start + timedelta(hours=h) for h in range(49)]

    def test_levels_row_h_is_the_forecast_h_hours_after_start(self):
        # wind is 50 mph only at start + 5 h, and calm otherwise
        start = datetime(2026, 11, 9, 12, tzinfo=UTC)
        fake = FakeWeather(lambda q: WeatherSample(50.0 if q.time == start + timedelta(hours=5) else 5.0, 0.0, 0.0))
        result, _, _ = run(weather=fake, load_weight_lb=20000.0)
        rows = levels(result)
        assert set(rows[5]) == {3}  # 45-54 mph is Severe for a light load
        for hour, row in enumerate(rows):
            if hour != 5:
                assert set(row) == {0}

    def test_the_last_row_is_hour_48(self):
        start = datetime(2026, 11, 9, 12, tzinfo=UTC)
        fake = FakeWeather(lambda q: WeatherSample(30.0 if q.time == start + timedelta(hours=48) else 5.0, 0.0, 0.0))
        result, _, _ = run(weather=fake)
        assert set(levels(result)[48]) == {1} and set(levels(result)[47]) == {0}


class TestLevelsMatchTheCheckpointRules:
    def test_each_condition(self):
        for sample, level in [
            (WeatherSample(30.0, 0.0, 0.0), 1),
            (WeatherSample(0.0, 0.3, 0.0), 2),
            (WeatherSample(0.0, 0.0, 2.5), 3),
            (WeatherSample(0.0, 1.2, 0.0), 4),
            (WeatherSample(0.0, 0.0, 0.0), 0),
        ]:
            result, _, _ = run(weather=FakeWeather(lambda q, s=sample: s))
            assert {l for row in levels(result) for l in row} == {level}

    def test_the_load_rules_are_applied(self):
        weather = FakeWeather(lambda q: WeatherSample(40.0, 0.0, 0.0))
        light, _, _ = run(weather=weather, load_weight_lb=40000.0)
        heavy, _, _ = run(weather=weather, load_weight_lb=40001.0)
        assert {l for row in levels(light) for l in row} == {2}  # 35-44 mph, not over 40,000 lb: High
        assert {l for row in levels(heavy) for l in row} == {3}  # over 40,000 lb: Severe

    def test_wind_50_with_a_heavy_load_is_no_travel(self):
        weather = FakeWeather(lambda q: WeatherSample(50.0, 0.0, 0.0))
        result, _, _ = run(weather=weather, load_weight_lb=30001.0)
        assert {l for row in levels(result) for l in row} == {4}

    def test_the_load_changes_the_levels_but_not_the_weather_asked_for(self):
        w1, w2 = FakeWeather(), FakeWeather()
        run(weather=w1, load_weight_lb=10000.0)
        run(weather=w2, load_weight_lb=70000.0)
        assert w1.calls == w2.calls

    def test_a_storm_in_one_place_lands_on_that_points_index(self):
        base, _, _ = run()
        points = base["points"]
        target = max(range(len(points)), key=lambda i: points[i][1])  # the most northern point
        lon, lat = points[target]
        fake = FakeWeather(lambda q: WeatherSample(60.0, 0.0, 0.0) if (q.lon, q.lat) == (lon, lat) else calm())
        result, _, _ = run(weather=fake)
        for row in levels(result):
            assert row[target] == 4
            assert sum(1 for level in row if level) == 1


class TestRoutesAndErrors:
    def test_the_routes_are_asked_for_once(self):
        _, routing, _ = run()
        assert len(routing.route_calls) == 1
        assert routing.route_calls[0][3] == 42000.0

    def test_the_grid_covers_every_route(self):
        import dataclasses

        first = recorded_route()
        # the same route moved 3 degrees north: a different corridor
        moved = dataclasses.replace(first, points=tuple((lat + 3.0, lon) for lat, lon in first.points))
        alone, _, _ = run(routes=[first])
        both, _, _ = run(routes=[first, moved])
        assert len(both["points"]) > len(alone["points"])
        assert max(lat for _, lat in both["points"]) >= max(lat for _, lat in alone["points"]) + 2.5
        assert set(map(tuple, alone["points"])) <= set(map(tuple, both["points"]))

    def test_an_identical_second_route_adds_nothing(self):
        alone, _, _ = run(routes=[recorded_route()])
        twice, _, _ = run(routes=[recorded_route(), recorded_route()])
        assert twice["points"] == alone["points"]

    def test_unknown_address(self):
        with pytest.raises(GeocodeNotFound) as caught:
            heatmap(request(origin="Atlantis"), FakeRouting([recorded_route()]), FakeWeather())
        assert caught.value.field == "origin"

    def test_same_place(self):
        routing = FakeRouting([recorded_route()], places={"Chicago, IL": CHICAGO, "chicago": CHICAGO})
        weather = FakeWeather()
        with pytest.raises(InvalidInput):
            heatmap(request(destination="chicago"), routing, weather)
        assert weather.calls == []

    def test_no_route(self):
        class NoRouteRouting(FakeRouting):
            def routes(self, *args):
                raise NoRoute("none")

        with pytest.raises(NoRoute):
            heatmap(request(), NoRouteRouting([]), FakeWeather())

    @pytest.mark.parametrize("error", [ForecastOutOfRange("x"), WeatherUnavailable("x")])
    def test_weather_failures_pass_through_and_no_partial_result(self, error):
        class Failing:
            def get_weather_at(self, queries):
                raise error

        with pytest.raises(type(error)):
            heatmap(request(), FakeRouting([recorded_route()]), Failing())


class TestScores:
    def test_calm_weather_is_zero_everywhere(self):
        result, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(0.0, 0.0, 0.0)))
        assert {s for row in result["scores"] for s in row} == {0.0}

    def test_different_low_winds_give_different_scores(self):
        # 5 mph and 20 mph are both Low, but the map must be able to tell them apart
        calm, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(5.0, 0.0, 0.0)))
        breezy, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(20.0, 0.0, 0.0)))
        assert {l for row in levels(calm) for l in row} == {l for row in levels(breezy) for l in row} == {0}
        assert {s for row in calm["scores"] for s in row} == {0.2}
        assert {s for row in breezy["scores"] for s in row} == {0.8}

    def test_the_score_of_each_hour_follows_that_hours_weather(self):
        start = datetime(2026, 11, 9, 12, tzinfo=UTC)
        fake = FakeWeather(lambda q: WeatherSample(float((q.time - start).total_seconds() // 3600), 0.0, 0.0))
        result, _, _ = run(weather=fake)
        for hour, row in enumerate(result["scores"]):
            expected = round(hour / 25, 2) if hour < 25 else None
            if expected is not None:
                assert set(row) == {expected}, hour

    def test_a_score_never_crosses_into_the_next_level_by_rounding(self):
        # wind 34.999 is Moderate; its score stays 1.99 (the top of the band), never 2.0
        result, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(34.999, 0.0, 0.0)))
        scores = {s for row in result["scores"] for s in row}
        assert scores == {1.99} and {l for row in levels(result) for l in row} == {1}

    def test_a_load_rule_lifts_the_score_to_the_start_of_the_level(self):
        weather = FakeWeather(lambda q: WeatherSample(40.0, 0.0, 0.0))
        light, _, _ = run(weather=weather, load_weight_lb=40000.0)
        heavy, _, _ = run(weather=weather, load_weight_lb=40001.0)
        assert {s for row in light["scores"] for s in row} == {2.5}
        assert {s for row in heavy["scores"] for s in row} == {3.0}

    def test_no_travel_is_exactly_four(self):
        result, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(60.0, 0.0, 0.0)))
        assert {s for row in result["scores"] for s in row} == {4.0}
