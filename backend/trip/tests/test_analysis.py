"""Tests for trip/analysis.py: the whole flow with fake TomTom and weather services."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from trip.analysis import analyze
from trip.errors import InvalidInput
from trip.sampling import METERS_PER_MILE
from trip.tests.helpers import CHICAGO, MADISON, FakeRouting, FakeWeather, calm, recorded_route
from trip.tomtom import GeocodeNotFound, NoRoute
from trip.validation import AnalyzeRequest
from trip.weather import ForecastOutOfRange, WeatherSample, WeatherUnavailable

UTC = timezone.utc
DEPART = datetime(2026, 11, 9, 12, 20, tzinfo=UTC)


def request(**override):
    base = dict(origin="Chicago, IL", destination="Madison, WI", departure=DEPART, load_weight_lb=42000.0, interval_miles=25)
    base.update(override)
    return AnalyzeRequest(**base)


def three_routes():
    return [recorded_route(), recorded_route(time_factor=1.2), recorded_route(time_factor=1.5)]


def run(routes=None, weather=None, **req):
    routing = FakeRouting(routes if routes is not None else three_routes())
    weather = weather or FakeWeather()
    return analyze(request(**req), routing, weather), routing, weather


def storm_after(lat, wind):
    """Wind ``wind`` mph everywhere north of ``lat``, calm elsewhere."""
    return lambda q: WeatherSample(wind, 0.0, 0.0) if q.lat > lat else calm()


# ---------------------------------------------------------------------------- response shape


class TestResponseShape:
    def test_top_level_and_route_keys_match_the_contract(self):
        result, _, _ = run()
        assert set(result) == {"origin", "destination", "routes", "recommendation"}
        route = result["routes"][0]
        assert set(route) == {"id", "summary", "geometry", "segments", "checkpoints"}
        assert set(route["summary"]) == {
            "distance_miles", "duration_minutes", "arrival", "miles_by_level",
            "severe_miles", "high_miles", "avg_risk", "has_no_travel",
        }
        assert set(route["summary"]["miles_by_level"]) == {"low", "moderate", "high", "severe", "no_travel"}
        assert set(route["checkpoints"][0]) == {
            "index", "mile", "lat", "lon", "eta", "represents_miles", "weather", "level_by", "level", "load_escalated",
        }
        assert set(route["checkpoints"][0]["weather"]) == {"wind_mph", "rain_in_hr", "snow_in_hr"}
        assert set(route["checkpoints"][0]["level_by"]) == {"wind", "rain", "snow"}
        assert set(route["segments"][0]) == {"level", "coordinates"}
        assert set(result["recommendation"]) == {
            "route_id", "decided_by", "versus_route_id", "duration_delta_minutes", "excluded_route_ids", "ranking",
        }

    def test_places_carry_query_label_and_position(self):
        result, _, _ = run()
        assert result["origin"] == {"query": "Chicago, IL", "label": "Chicago, IL", "lat": 41.883229, "lon": -87.632398}
        assert result["destination"]["label"] == "Madison, WI"

    def test_route_ids_follow_the_routing_order(self):
        result, _, _ = run()
        assert [r["id"] for r in result["routes"]] == ["A", "B", "C"]

    def test_fewer_than_three_routes_are_returned_as_they_are(self):
        result, _, _ = run(routes=[recorded_route()])
        assert [r["id"] for r in result["routes"]] == ["A"]
        assert result["recommendation"]["route_id"] == "A"
        assert result["recommendation"]["decided_by"] == "only_candidate"

    def test_the_result_is_plain_json(self):
        result, _, _ = run()
        text = json.dumps(result, allow_nan=False)  # no NaN / inf / non-serialisable objects
        assert json.loads(text) == result

    def test_levels_are_lowercase_api_names(self):
        result, _, _ = run(weather=FakeWeather(storm_after(42.5, 40.0)))
        levels = {c["level"] for r in result["routes"] for c in r["checkpoints"]}
        assert levels <= {"low", "moderate", "high", "severe", "no_travel"} and "severe" in levels


# ------------------------------------------------------------------------ rounding and times


class TestRoundingAtTheEdge:
    def test_response_numbers_are_rounded_for_display(self):
        result, _, _ = run()
        for route in result["routes"]:
            for cp in route["checkpoints"]:
                assert cp["lat"] == round(cp["lat"], 5) and cp["lon"] == round(cp["lon"], 5)
                assert cp["mile"] == round(cp["mile"], 2)
                assert cp["represents_miles"] == round(cp["represents_miles"], 2)
            for lon, lat in route["geometry"]:
                assert (lon, lat) == (round(lon, 5), round(lat, 5))

    def test_times_are_utc_iso_to_the_second(self):
        result, _, _ = run()
        for route in result["routes"]:
            for cp in route["checkpoints"]:
                assert cp["eta"].endswith("Z") and datetime.strptime(cp["eta"], "%Y-%m-%dT%H:%M:%SZ")
            assert route["summary"]["arrival"].endswith("Z")

    def test_the_first_checkpoint_is_the_departure_and_the_last_is_the_arrival(self):
        result, _, _ = run()
        for route in result["routes"]:
            assert route["checkpoints"][0]["eta"] == "2026-11-09T12:20:00Z"
            assert route["checkpoints"][-1]["eta"] == route["summary"]["arrival"]

    def test_etas_never_go_backwards(self):
        result, _, _ = run()
        for route in result["routes"]:
            etas = [c["eta"] for c in route["checkpoints"]]
            assert etas == sorted(etas)

    def test_departure_in_another_zone_gives_the_same_utc_times(self):
        seoul = timezone(timedelta(hours=9))
        a, _, _ = run(departure=DEPART)
        b, _, _ = run(departure=DEPART.astimezone(seoul))
        assert a == b


# ------------------------------------------------------------------------------- checkpoints


class TestCheckpointsAndMiles:
    def test_interval_sets_the_number_of_checkpoints(self):
        counts = {}
        for interval in (10, 25, 50):
            result, _, _ = run(routes=[recorded_route()], interval_miles=interval)
            counts[interval] = len(result["routes"][0]["checkpoints"])
        assert counts == {10: 17, 25: 8, 50: 5}

    def test_represented_miles_add_up_to_the_distance(self):
        result, _, _ = run()
        for route in result["routes"]:
            total = sum(c["represents_miles"] for c in route["checkpoints"])
            assert total == pytest.approx(route["summary"]["distance_miles"], abs=0.5)
            assert route["checkpoints"][-1]["mile"] == pytest.approx(route["summary"]["distance_miles"], abs=0.5)

    def test_level_miles_add_up_to_the_distance_within_rounding(self):
        result, _, _ = run(weather=FakeWeather(storm_after(42.4, 40.0)))
        for route in result["routes"]:
            s = route["summary"]
            assert abs(sum(s["miles_by_level"].values()) - s["distance_miles"]) <= 2.5

    def test_there_is_one_weather_call_for_every_checkpoint_of_every_route(self):
        _, _, weather = run()
        assert len(weather.calls) == 1
        assert len(weather.calls[0]) == 3 * 8

    def test_weather_is_asked_at_each_checkpoints_position_and_eta(self):
        result, _, weather = run(routes=[recorded_route()])
        for query, cp in zip(weather.calls[0], result["routes"][0]["checkpoints"]):
            assert (round(query.lat, 5), round(query.lon, 5)) == (cp["lat"], cp["lon"])
            assert query.time.strftime("%Y-%m-%dT%H:%M:%SZ") == cp["eta"]

    def test_a_slower_route_arrives_later_at_the_same_places(self):
        result, _, _ = run()
        a, b, c = (r["checkpoints"][-1]["eta"] for r in result["routes"])
        assert a < b < c


# --------------------------------------------------------------------------------- the risk


class TestRiskFlow:
    def test_wind_rain_and_snow_each_set_their_level(self):
        samples = iter([
            WeatherSample(30.0, 0.0, 0.0),   # wind moderate
            WeatherSample(0.0, 0.3, 0.0),    # rain high
            WeatherSample(0.0, 0.0, 2.5),    # snow severe
            WeatherSample(0.0, 1.2, 0.0),    # rain no travel
        ] + [WeatherSample(0.0, 0.0, 0.0)] * 20)
        result, _, _ = run(routes=[recorded_route()], weather=FakeWeather(lambda q: next(samples)))
        cps = result["routes"][0]["checkpoints"]
        assert [c["level"] for c in cps[:4]] == ["moderate", "high", "severe", "no_travel"]
        assert cps[1]["level_by"] == {"wind": "low", "rain": "high", "snow": "low"}

    def test_the_load_rule_raises_a_level_and_says_so(self):
        weather = FakeWeather(lambda q: WeatherSample(40.0, 0.0, 0.0))
        heavy, _, _ = run(routes=[recorded_route()], weather=weather, load_weight_lb=45000.0)
        light, _, _ = run(routes=[recorded_route()], weather=weather, load_weight_lb=20000.0)
        assert {c["level"] for c in heavy["routes"][0]["checkpoints"]} == {"severe"}
        assert all(c["load_escalated"] for c in heavy["routes"][0]["checkpoints"])
        assert {c["level"] for c in light["routes"][0]["checkpoints"]} == {"high"}
        assert not any(c["load_escalated"] for c in light["routes"][0]["checkpoints"])
        assert heavy["routes"][0]["checkpoints"][0]["level_by"]["wind"] == "high"  # base level is kept

    def test_the_load_weight_only_changes_levels_not_the_weather_asked_for(self):
        w1, w2 = FakeWeather(), FakeWeather()
        run(weather=w1, load_weight_lb=10000.0)
        run(weather=w2, load_weight_lb=70000.0)
        assert w1.calls == w2.calls

    def test_load_weight_is_passed_to_routing_in_pounds(self):
        _, routing, _ = run(load_weight_lb=42000.0)
        assert routing.route_calls[0][3] == 42000.0

    def test_no_travel_flags_the_route(self):
        result, _, _ = run(weather=FakeWeather(storm_after(42.4, 60.0)))
        assert all(r["summary"]["has_no_travel"] for r in result["routes"])

    def test_wind_45_to_54_with_a_heavy_load_is_no_travel(self):
        weather = FakeWeather(lambda q: WeatherSample(50.0, 0.0, 0.0))
        heavy, _, _ = run(routes=[recorded_route()], weather=weather, load_weight_lb=31000.0)
        light, _, _ = run(routes=[recorded_route()], weather=weather, load_weight_lb=30000.0)
        assert heavy["routes"][0]["summary"]["has_no_travel"] is True
        assert light["routes"][0]["summary"]["has_no_travel"] is False  # exactly 30,000 lb is not over


# ------------------------------------------------------------------------------- the segments


class TestSegments:
    def test_segments_follow_the_runs_of_checkpoint_levels(self):
        # storm for the north part only
        result, _, _ = run(routes=[recorded_route()], weather=FakeWeather(storm_after(43.0, 40.0)))
        route = result["routes"][0]
        runs = []
        for cp in route["checkpoints"]:
            if not runs or runs[-1] != cp["level"]:
                runs.append(cp["level"])
        assert [s["level"] for s in route["segments"]] == runs and len(runs) > 1

    def test_segments_join_and_make_the_geometry(self):
        result, _, _ = run(weather=FakeWeather(storm_after(42.6, 40.0)))
        for route in result["routes"]:
            segs = route["segments"]
            for a, b in zip(segs, segs[1:]):
                assert a["coordinates"][-1] == b["coordinates"][0]
            rebuilt = [c for i, s in enumerate(segs) for c in (s["coordinates"] if i == 0 else s["coordinates"][1:])]
            assert route["geometry"] == rebuilt

    def test_the_line_runs_from_origin_to_destination(self):
        result, _, _ = run(routes=[recorded_route()])
        geometry = result["routes"][0]["geometry"]
        start = result["routes"][0]["checkpoints"][0]
        end = result["routes"][0]["checkpoints"][-1]
        assert geometry[0] == [start["lon"], start["lat"]]
        assert geometry[-1] == [end["lon"], end["lat"]]

    def test_the_geometry_is_much_smaller_than_the_route(self):
        route = recorded_route()
        result, _, _ = run(routes=[route])
        assert len(result["routes"][0]["geometry"]) < len(route.points) / 3

    def test_a_cut_is_where_a_stretch_ends(self):
        # The level changes after checkpoint 2 (mile 50), so the cut is half way to mile 75: mile 62.5.
        samples = iter([calm()] * 3 + [WeatherSample(40.0, 0.0, 0.0)] * 20)
        raw = recorded_route()
        result, _, _ = run(routes=[raw], weather=FakeWeather(lambda q: next(samples)))
        route = result["routes"][0]
        assert sum(c["represents_miles"] for c in route["checkpoints"][:3]) == pytest.approx(62.5)

        from trip.sampling import interpolate, route_distances_m
        distances = route_distances_m(raw.points, raw.anchors, raw.length_m, raw.time_s)
        meters = 62.5 * METERS_PER_MILE
        expected_lat = interpolate(distances, [p[0] for p in raw.points], meters)
        expected_lon = interpolate(distances, [p[1] for p in raw.points], meters)
        cut_lon, cut_lat = route["segments"][1]["coordinates"][0]
        assert (cut_lon, cut_lat) == (round(expected_lon, 5), round(expected_lat, 5))

    def test_checkpoint_miles_keep_two_decimals(self):
        raw = recorded_route()
        result, _, _ = run(routes=[raw])
        last = result["routes"][0]["checkpoints"][-1]
        assert last["mile"] == round(raw.length_m / METERS_PER_MILE, 2)
        assert last["mile"] != round(last["mile"])  # 156.55, not 157


# ---------------------------------------------------------------------------- recommendation


class TestRecommendationFlow:
    def test_a_storm_on_every_route_ties_and_the_fastest_listed_first_wins(self):
        result, _, _ = run()
        rec = result["recommendation"]
        assert (rec["route_id"], rec["decided_by"], rec["versus_route_id"]) == ("A", "duration", "B")
        assert rec["duration_delta_minutes"] < 0 and rec["ranking"] == ["A", "B", "C"]

    def test_a_route_with_no_travel_is_excluded_and_the_next_one_recommended(self):
        # A arrives 14:55, B 15:26, C 16:12. A storm after 15:00 UTC is reached by B and C only.
        late = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
        weather = FakeWeather(lambda q: WeatherSample(60.0, 0.0, 0.0) if q.time > late else calm())
        result, _, _ = run(weather=weather)
        rec = result["recommendation"]
        flags = {r["id"]: r["summary"]["has_no_travel"] for r in result["routes"]}
        assert flags == {"A": False, "B": True, "C": True}
        assert rec["route_id"] == "A" and rec["excluded_route_ids"] == ["B", "C"]
        assert rec["decided_by"] == "only_candidate" and rec["ranking"] == ["A"]

    def test_all_routes_no_travel_means_no_recommendation(self):
        result, _, _ = run(weather=FakeWeather(lambda q: WeatherSample(60.0, 0.0, 0.0)))
        rec = result["recommendation"]
        assert rec == {
            "route_id": None, "decided_by": None, "versus_route_id": None,
            "duration_delta_minutes": None, "excluded_route_ids": ["A", "B", "C"], "ranking": [],
        }
        assert len(result["routes"]) == 3  # the routes are still shown

    def test_weather_that_depends_on_time_makes_the_better_route_win(self):
        # bad weather only after 13:30 UTC: the slower routes reach it, the fastest does not
        cutoff = datetime(2026, 11, 9, 13, 30, tzinfo=UTC)
        weather = FakeWeather(lambda q: WeatherSample(40.0, 0.0, 0.0) if q.time > cutoff else calm())
        result, _, _ = run(weather=weather, load_weight_lb=20000.0)
        rec = result["recommendation"]
        highs = {r["id"]: r["summary"]["high_miles"] for r in result["routes"]}
        assert highs["A"] <= highs["B"] <= highs["C"]
        assert rec["route_id"] == "A"

    def test_the_load_can_change_the_recommendation(self):
        # 50 mph on the second half: light load Severe, heavy load No Travel on every route
        weather = FakeWeather(storm_after(42.8, 50.0))
        light, _, _ = run(weather=weather, load_weight_lb=20000.0)
        heavy, _, _ = run(weather=weather, load_weight_lb=40000.0)
        assert light["recommendation"]["route_id"] == "A"
        assert heavy["recommendation"]["route_id"] is None


# ------------------------------------------------------------------------------------ errors


class TestErrors:
    def test_unknown_origin_is_tagged_with_its_field(self):
        routing = FakeRouting(three_routes())
        with pytest.raises(GeocodeNotFound) as caught:
            analyze(request(origin="Atlantis"), routing, FakeWeather())
        assert caught.value.field == "origin"

    def test_unknown_destination_is_tagged_with_its_field(self):
        with pytest.raises(GeocodeNotFound) as caught:
            analyze(request(destination="Atlantis"), FakeRouting(three_routes()), FakeWeather())
        assert caught.value.field == "destination"

    def test_nothing_else_is_called_after_a_geocoding_failure(self):
        routing, weather = FakeRouting(three_routes()), FakeWeather()
        with pytest.raises(GeocodeNotFound):
            analyze(request(origin="Atlantis"), routing, weather)
        assert routing.route_calls == [] and weather.calls == []

    def test_the_same_place_is_refused_before_routing(self):
        routing = FakeRouting(three_routes(), places={"Chicago, IL": CHICAGO, "chicago": CHICAGO})
        with pytest.raises(InvalidInput) as caught:
            analyze(request(destination="chicago"), routing, FakeWeather())
        assert caught.value.field == "destination" and routing.route_calls == []

    def test_places_a_metre_apart_count_as_the_same(self):
        near = CHICAGO.__class__("near", "Near", CHICAGO.lat + 0.000001, CHICAGO.lon)
        routing = FakeRouting(three_routes(), places={"Chicago, IL": CHICAGO, "near": near})
        with pytest.raises(InvalidInput):
            analyze(request(destination="near"), routing, FakeWeather())

    def test_places_a_few_metres_apart_are_different_places(self):
        # 0.0005 degrees is about 55 m: a real (very short) trip, not "the same place"
        near = CHICAGO.__class__("near", "Near", CHICAGO.lat + 0.0005, CHICAGO.lon)
        east = CHICAGO.__class__("east", "East", CHICAGO.lat, CHICAGO.lon + 0.0005)
        for other in (near, east):
            routing = FakeRouting([recorded_route()], places={"Chicago, IL": CHICAGO, other.query: other})
            result = analyze(request(destination=other.query), routing, FakeWeather())
            assert len(result["routes"]) == 1

    def test_a_route_of_length_zero_is_refused(self):
        from trip.tomtom import RawRoute
        zero = RawRoute(points=((41.0, -87.0), (41.0, -87.0)), anchors=(), length_m=0.0, time_s=0.0)
        weather = FakeWeather()
        with pytest.raises(InvalidInput) as caught:
            run(routes=[zero], weather=weather)
        assert caught.value.field == "destination" and weather.calls == []

    def test_no_route_passes_through(self):
        class NoRouteRouting(FakeRouting):
            def routes(self, *args):
                raise NoRoute("none")
        with pytest.raises(NoRoute):
            analyze(request(), NoRouteRouting([]), FakeWeather())

    @pytest.mark.parametrize("error", [ForecastOutOfRange("x"), WeatherUnavailable("x")])
    def test_weather_failures_pass_through(self, error):
        class Failing:
            def get_weather_at(self, queries):
                raise error
        with pytest.raises(type(error)):
            analyze(request(), FakeRouting(three_routes()), Failing())
