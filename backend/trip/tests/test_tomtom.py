"""Tests for trip/tomtom.py with a fake HTTP session (no network)."""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from trip import tomtom as tomtom_module
from trip.sampling import Anchor
from trip.tests.fakes import DictCache, FakeResponse, FakeSession
from trip.tomtom import (
    BASE_URL,
    GeocodeNotFound,
    NoRoute,
    Place,
    RawRoute,
    RoutingUnavailable,
    TomTomClient,
)

UTC = timezone.utc
KEY = "SECRET-KEY-123"
DEPART = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
CHICAGO = Place("Chicago, IL", "Chicago, IL", 41.883229, -87.632398)
DENVER = Place("Denver, CO", "Denver, CO", 39.738453, -104.984853)


def geocode_body(label="Chicago, IL", lat=41.883229, lon=-87.632398):
    return {"summary": {"numResults": 1}, "results": [{"address": {"freeformAddress": label}, "position": {"lat": lat, "lon": lon}}]}


def route_json(points, instructions, length=1000, time=100):
    return {
        "summary": {"lengthInMeters": length, "travelTimeInSeconds": time},
        "legs": [{"points": [{"latitude": la, "longitude": lo} for la, lo in points]}],
        "guidance": {"instructions": [{"pointIndex": i, "routeOffsetInMeters": o, "travelTimeInSeconds": t} for i, o, t in instructions]},
    }


ROUTE_A = route_json([(41.0, -87.0), (41.1, -87.1), (41.2, -87.2)], [(0, 0, 0), (1, 600, 60), (2, 1000, 100)])


def make(handler, cache=None, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    session = FakeSession(handler)
    return TomTomClient(KEY, session=session, cache=cache or DictCache(), sleep=sleeps.append), session, sleeps


def routes_handler(routes=None):
    return lambda url, params: FakeResponse(200, {"routes": [ROUTE_A] if routes is None else routes})


# --------------------------------------------------------------------------------- geocode


class TestGeocode:
    def test_a_match(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, geocode_body("Chicago, IL", 41.88, -87.63)))
        place = client.geocode("Chicago, IL")
        assert place == Place(query="Chicago, IL", label="Chicago, IL", lat=41.88, lon=-87.63)

    def test_request_shape(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, geocode_body()))
        client.geocode("  Chicago, IL ")
        [(url, params)] = session.calls
        assert url == f"{BASE_URL}/search/2/geocode/Chicago%2C%20IL.json"
        assert params == {"countrySet": "US", "limit": 1, "key": KEY}

    def test_special_characters_are_escaped_in_the_path(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, geocode_body()))
        client.geocode("1 Main St/Apt #5? 60601")
        url = session.calls[0][0]
        assert url.endswith(".json") and "#" not in url and "?" not in url
        assert url.count("/") == BASE_URL.count("/") + 4  # /search/2/geocode/<one segment>.json

    def test_no_result(self):
        client, _, _ = make(lambda u, p: FakeResponse(200, {"summary": {"numResults": 0}, "results": []}))
        with pytest.raises(GeocodeNotFound) as caught:
            client.geocode("zzzz")
        assert caught.value.query == "zzzz" and caught.value.field is None

    def test_the_query_is_kept_as_typed_and_the_label_comes_from_tomtom(self):
        client, _, _ = make(lambda u, p: FakeResponse(200, geocode_body("Chicago, IL")))
        assert client.geocode("chicago").query == "chicago"
        assert client.geocode("chicago").label == "Chicago, IL"

    def test_a_missing_label_falls_back_to_the_query(self):
        body = {"results": [{"address": {}, "position": {"lat": 1.0, "lon": 2.0}}]}
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        assert client.geocode(" Somewhere ").label == "Somewhere"

    @pytest.mark.parametrize(
        "body",
        [{}, {"results": None}, {"results": [{}]}, {"results": [{"position": {"lat": "x", "lon": 1}}]}, {"results": [{"position": None}]}, "oops", None],
    )
    def test_unreadable_answers(self, body):
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        with pytest.raises(RoutingUnavailable, match="cannot be read"):
            client.geocode("Chicago")

    def test_a_repeat_is_served_from_the_cache_ignoring_case_and_spaces(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, geocode_body()))
        client.geocode("Chicago, IL")
        client.geocode("  chicago, il ")
        assert len(session.calls) == 1

    def test_a_miss_is_not_cached(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, {"results": []}))
        for _ in range(2):
            with pytest.raises(GeocodeNotFound):
                client.geocode("zzzz")
        assert len(session.calls) == 2

    def test_a_400_is_unavailable(self):
        client, _, _ = make(lambda u, p: FakeResponse(400, {"detailedError": {}}))
        with pytest.raises(RoutingUnavailable, match="HTTP 400"):
            client.geocode("x")


# ----------------------------------------------------------------------------------- routes


class TestRouteRequest:
    def test_parameters(self):
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, 42000)
        [(url, params)] = session.calls
        assert url == f"{BASE_URL}/routing/1/calculateRoute/41.883229,-87.632398:39.738453,-104.984853/json"
        assert params == {
            "travelMode": "truck",
            "vehicleCommercial": "true",
            "vehicleWeight": 19051,
            "maxAlternatives": 2,
            "departAt": "2026-11-10T14:00:00Z",
            "instructionsType": "coded",
            "key": KEY,
        }

    @pytest.mark.parametrize("lb, kg", [(0, 0), (1, 0), (2, 1), (20000, 9072), (42000, 19051), (80000, 36287), (1_000_000, 453592)])
    def test_pounds_are_converted_to_kilograms(self, lb, kg):
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, lb)
        assert session.calls[0][1]["vehicleWeight"] == kg

    def test_departure_is_sent_in_utc(self):
        seoul = timezone(timedelta(hours=9))
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, datetime(2026, 11, 10, 23, 30, 15, 999, tzinfo=seoul), 1000)
        assert session.calls[0][1]["departAt"] == "2026-11-10T14:30:15Z"


class TestRouteParsing:
    def test_points_anchors_and_totals(self):
        client, _, _ = make(routes_handler())
        [route] = client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert route == RawRoute(
            points=((41.0, -87.0), (41.1, -87.1), (41.2, -87.2)),
            anchors=(Anchor(0, 0.0, 0.0), Anchor(1, 600.0, 60.0), Anchor(2, 1000.0, 100.0)),
            length_m=1000.0,
            time_s=100.0,
        )

    def test_the_order_of_routes_is_tomtoms(self):
        slow = route_json([(1.0, 1.0), (2.0, 2.0)], [(0, 0, 0), (1, 500, 900)], length=500, time=900)
        client, _, _ = make(routes_handler([ROUTE_A, slow]))
        routes = client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert [r.length_m for r in routes] == [1000.0, 500.0]

    def test_at_most_three_routes(self):
        client, _, _ = make(routes_handler([ROUTE_A] * 5))
        assert len(client.routes(CHICAGO, DENVER, DEPART, 1000)) == 3

    def test_fewer_than_three_are_passed_on(self):
        client, _, _ = make(routes_handler([ROUTE_A, ROUTE_A]))
        assert len(client.routes(CHICAGO, DENVER, DEPART, 1000)) == 2

    def test_legs_are_joined_without_repeating_the_shared_point(self):
        two_legs = {
            "summary": {"lengthInMeters": 10, "travelTimeInSeconds": 1},
            "legs": [
                {"points": [{"latitude": 1.0, "longitude": 1.0}, {"latitude": 2.0, "longitude": 2.0}]},
                {"points": [{"latitude": 2.0, "longitude": 2.0}, {"latitude": 3.0, "longitude": 3.0}]},
            ],
        }
        client, _, _ = make(routes_handler([two_legs]))
        [route] = client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert route.points == ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0))

    @pytest.mark.parametrize("guidance", [None, {}, {"instructions": []}, {"instructions": None}])
    def test_missing_guidance_gives_no_anchors(self, guidance):
        raw = {k: v for k, v in ROUTE_A.items() if k != "guidance"}
        if guidance is not None:
            raw["guidance"] = guidance
        client, _, _ = make(routes_handler([raw]))
        assert client.routes(CHICAGO, DENVER, DEPART, 1000)[0].anchors == ()

    @pytest.mark.parametrize(
        "body",
        [{}, {"routes": None}, {"routes": [{}]}, {"routes": [{"summary": {}, "legs": []}]}, {"routes": ["x"]}, "oops", None, {"routes": [{"summary": {"lengthInMeters": "x", "travelTimeInSeconds": 1}, "legs": [{"points": []}]}]}],
    )
    def test_unreadable_answers(self, body):
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        with pytest.raises(RoutingUnavailable, match="cannot be read"):
            client.routes(CHICAGO, DENVER, DEPART, 1000)

    def test_an_empty_route_list_is_no_route(self):
        client, _, _ = make(routes_handler([]))
        with pytest.raises(NoRoute):
            client.routes(CHICAGO, DENVER, DEPART, 1000)


class TestRouteErrors:
    @pytest.mark.parametrize("code", ["NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"])
    def test_no_route_codes(self, code):
        body = {"detailedError": {"code": code, "message": "Engine error ..."}}
        client, session, _ = make(lambda u, p: FakeResponse(400, body))
        with pytest.raises(NoRoute):
            client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert len(session.calls) == 1  # not retried

    def test_other_bad_requests_are_unavailable_not_no_route(self):
        client, _, _ = make(lambda u, p: FakeResponse(400, {"detailedError": {"code": "INVALID_PARAMETER"}}))
        with pytest.raises(RoutingUnavailable, match="INVALID_PARAMETER"):
            client.routes(CHICAGO, DENVER, DEPART, 1000)

    @pytest.mark.parametrize("body", [None, "text", {}, {"detailedError": None}, {"detailedError": "x"}])
    def test_a_bad_request_without_a_readable_code(self, body):
        client, _, _ = make(lambda u, p: FakeResponse(400, body))
        with pytest.raises(RoutingUnavailable):
            client.routes(CHICAGO, DENVER, DEPART, 1000)

    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_key_and_other_client_errors_are_unavailable_without_retry(self, status):
        client, session, sleeps = make(lambda u, p: FakeResponse(status, {"detailedError": {"code": "Unauthorized"}}))
        with pytest.raises(RoutingUnavailable, match=str(status)):
            client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert len(session.calls) == 1 and sleeps == []

    def test_rate_limit_then_success(self):
        answers = [FakeResponse(429, {}), None]
        client, session, sleeps = make(lambda u, p: answers.pop(0) or FakeResponse(200, {"routes": [ROUTE_A]}))
        assert len(client.routes(CHICAGO, DENVER, DEPART, 1000)) == 1
        assert len(session.calls) == 2 and sleeps == [1.0]

    def test_gives_up_after_three_attempts(self):
        client, session, sleeps = make(lambda u, p: FakeResponse(503, {}))
        with pytest.raises(RoutingUnavailable, match=r"TomTom is not responding \(HTTP 503\)"):
            client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert len(session.calls) == 3 and sleeps == [1.0, 2.0]

    @pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
    def test_network_failures(self, error):
        client, session, _ = make(lambda u, p: error)
        with pytest.raises(RoutingUnavailable, match=type(error).__name__):
            client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert len(session.calls) == 3


class TestTimeout:
    def test_calls_wait_long_enough_for_a_cross_country_answer(self):
        # a 3-route answer takes 6 to 10 seconds (CLAUDE.md section 7)
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert session.timeouts == [tomtom_module.REQUEST_TIMEOUT_SECONDS]
        assert tomtom_module.REQUEST_TIMEOUT_SECONDS >= 30


class TestApiKeyNeverLeaks:
    @pytest.mark.parametrize(
        "handler",
        [
            lambda u, p: FakeResponse(401, {}),
            lambda u, p: FakeResponse(500, {}),
            lambda u, p: FakeResponse(200, not_json=True),
            lambda u, p: FakeResponse(400, {"detailedError": {"code": "X"}}),
            lambda u, p: requests.ConnectionError(f"failed for {u}?key={KEY}"),
            lambda u, p: FakeResponse(200, {"routes": [{}]}),
        ],
        ids=["401", "500", "not-json", "400", "network", "unreadable"],
    )
    def test_no_error_message_contains_the_key_or_the_url(self, handler):
        client, _, _ = make(handler)
        with pytest.raises(RoutingUnavailable) as caught:
            client.routes(CHICAGO, DENVER, DEPART, 1000)
        message = str(caught.value)
        assert KEY not in message and "tomtom.com" not in message

    def test_the_key_is_sent_as_a_parameter_on_every_call(self):
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert all(params["key"] == KEY for _, params in session.calls)


class TestRouteCache:
    def test_a_different_destination_is_a_new_request(self):
        client, session, _ = make(routes_handler())
        madison = Place("Madison, WI", "Madison, WI", 43.074761, -89.383761)
        client.routes(CHICAGO, DENVER, DEPART, 42000)
        client.routes(CHICAGO, madison, DEPART, 42000)
        assert len(session.calls) == 2

    def test_a_different_origin_is_a_new_request(self):
        client, session, _ = make(routes_handler())
        madison = Place("Madison, WI", "Madison, WI", 43.074761, -89.383761)
        client.routes(CHICAGO, DENVER, DEPART, 42000)
        client.routes(madison, DENVER, DEPART, 42000)
        assert len(session.calls) == 2

    def test_the_same_request_is_not_sent_twice(self):
        client, session, _ = make(routes_handler())
        first = client.routes(CHICAGO, DENVER, DEPART, 42000)
        second = client.routes(CHICAGO, DENVER, DEPART, 42000)
        assert len(session.calls) == 1 and first == second

    @pytest.mark.parametrize(
        "args",
        [
            (DENVER, CHICAGO, DEPART, 42000),
            (CHICAGO, DENVER, DEPART + timedelta(minutes=1), 42000),
            (CHICAGO, DENVER, DEPART, 50000),
        ],
        ids=["swapped ends", "other departure", "other weight"],
    )
    def test_any_changed_input_is_a_new_request(self, args):
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, 42000)
        client.routes(*args)
        assert len(session.calls) == 2

    def test_the_same_departure_in_another_zone_hits_the_cache(self):
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, 42000)
        client.routes(CHICAGO, DENVER, DEPART.astimezone(timezone(timedelta(hours=-6))), 42000)
        assert len(session.calls) == 1

    def test_weights_that_round_to_the_same_kilogram_share_an_entry(self):
        client, session, _ = make(routes_handler())
        client.routes(CHICAGO, DENVER, DEPART, 42000.0)
        client.routes(CHICAGO, DENVER, DEPART, 42000.5)
        assert len(session.calls) == 1

    def test_failures_are_not_cached(self):
        client, session, _ = make(lambda u, p: FakeResponse(400, {"detailedError": {"code": "NO_ROUTE_FOUND"}}))
        for _ in range(2):
            with pytest.raises(NoRoute):
                client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert len(session.calls) == 2


def test_an_api_key_is_required():
    with pytest.raises(ValueError):
        TomTomClient("")
