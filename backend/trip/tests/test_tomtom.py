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
    LocationNotCovered,
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
        assert url == f"{BASE_URL}/search/2/search/Chicago%2C%20IL.json"
        assert params == {"countrySet": "US", "limit": 1, "key": KEY}

    def test_special_characters_are_escaped_in_the_path(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, geocode_body()))
        client.geocode("1 Main St/Apt #5? 60601")
        url = session.calls[0][0]
        assert url.endswith(".json") and "#" not in url and "?" not in url
        assert url.count("/") == BASE_URL.count("/") + 4  # /search/2/search/<one segment>.json

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

    def test_a_400_means_the_text_cannot_be_found(self):
        # TomTom answers 400 to a text it cannot search for ("%%%"): the text is the problem.
        client, _, _ = make(lambda u, p: FakeResponse(400, {"detailedError": {}}))
        with pytest.raises(GeocodeNotFound):
            client.geocode("%%%")

    def test_a_cached_place_carries_the_callers_own_spelling(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, geocode_body("Chicago, IL")))
        first = client.geocode("Chicago, IL")
        second = client.geocode("CHICAGO, il")
        assert len(session.calls) == 1
        assert (first.query, second.query) == ("Chicago, IL", "CHICAGO, il")
        assert (second.label, second.lat, second.lon) == (first.label, first.lat, first.lon)


    def test_a_named_place_keeps_its_name_in_the_label(self):
        body = {"results": [{"type": "POI", "poi": {"name": "Willis Tower"}, "address": {"freeformAddress": "233 South Wacker Drive, Chicago, IL 60606"}, "position": {"lat": 41.8789, "lon": -87.6359}}]}
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        assert client.geocode("Willis Tower, Chicago").label == "Willis Tower, 233 South Wacker Drive, Chicago, IL 60606"


# -------------------------------------------------------------------------------- suggest


def result(kind="Point Address", free="233 South Wacker Drive, Chicago, IL 60606", poi=None, lat=41.8789, lon=-87.6354, id="id1"):
    item = {"type": kind, "id": id, "address": {"freeformAddress": free}, "position": {"lat": lat, "lon": lon}}
    if poi:
        item["poi"] = {"name": poi}
    return item


def results_handler(*items):
    return lambda url, params: FakeResponse(200, {"results": list(items)})


class TestSuggest:
    def test_request_shape(self):
        client, session, _ = make(results_handler(result()))
        client.suggest("  233   S Wack ")
        [(url, params)] = session.calls
        assert url == f"{BASE_URL}/search/2/search/233%20S%20Wack.json"
        assert params == {"countrySet": "US", "limit": 10, "typeahead": "true", "key": KEY}

    def test_a_named_place_has_its_name_first_and_the_address_under_it(self):
        client, _, _ = make(results_handler(result("POI", poi="Willis Tower", id="p1")))
        [item] = client.suggest("willis tow")
        assert (item.kind, item.name, item.id) == ("place", "Willis Tower", "p1")
        assert item.detail == "233 South Wacker Drive, Chicago, IL 60606"
        assert item.label == "Willis Tower, 233 South Wacker Drive, Chicago, IL 60606"
        assert (item.lat, item.lon) == (41.8789, -87.6354)

    def test_an_address_is_split_into_street_and_the_rest(self):
        client, _, _ = make(results_handler(result()))
        [item] = client.suggest("233 s wack")
        assert item.kind == "address"
        assert (item.name, item.detail) == ("233 South Wacker Drive", "Chicago, IL 60606")
        assert item.label == "233 South Wacker Drive, Chicago, IL 60606"

    def test_a_city_is_an_area(self):
        client, _, _ = make(results_handler(result("Geography", "Chicago, IL")))
        [item] = client.suggest("chicago")
        assert (item.kind, item.name, item.detail, item.label) == ("area", "Chicago", "IL", "Chicago, IL")

    def test_the_same_place_listed_twice_is_shown_once(self):
        twice = [result("POI", poi="Willis Tower", id="a"), result("POI", poi="Willis Tower", lat=41.88, id="b")]
        client, _, _ = make(results_handler(*twice, result("POI", poi="Willis Tower", free="205 West Monroe Street, Chicago, IL 60606", id="c")))
        assert [i.id for i in client.suggest("willis tower")] == ["a", "c"]

    def test_at_most_five_in_tomtoms_order(self):
        items = [result(free=f"{n} Main Street, Springfield, IL", id=str(n)) for n in range(1, 9)]
        client, _, _ = make(results_handler(*items))
        assert [i.id for i in client.suggest("main")] == ["1", "2", "3", "4", "5"]

    def test_an_unreadable_result_is_skipped_but_the_rest_is_kept(self):
        client, _, _ = make(results_handler({"type": "POI"}, {"position": {"lat": "x", "lon": 1}}, result(id="ok")))
        assert [i.id for i in client.suggest("wacker")] == ["ok"]

    def test_a_result_without_any_text_is_skipped(self):
        client, _, _ = make(results_handler(result(free="", id="blank"), result(id="ok")))
        assert [i.id for i in client.suggest("wacker")] == ["ok"]

    def test_a_missing_id_falls_back_to_the_position(self):
        item = result()
        del item["id"]
        client, _, _ = make(results_handler(item))
        assert client.suggest("wacker")[0].id == "41.87890,-87.63540"

    @pytest.mark.parametrize("text", ["", " ", "a", " a ", "ab", "  ab  ", "a ", " b"])
    def test_too_short_makes_no_call(self, text):
        client, session, _ = make(results_handler(result()))
        assert client.suggest(text) == []
        assert session.calls == []

    def test_three_characters_are_enough(self):
        client, session, _ = make(results_handler(result()))
        client.suggest("chi")
        assert len(session.calls) == 1

    def test_no_results_is_an_empty_list(self):
        client, _, _ = make(results_handler())
        assert client.suggest("zzzz") == []

    def test_a_repeat_is_served_from_the_cache_ignoring_case_and_spaces(self):
        client, session, _ = make(results_handler(result()))
        first = client.suggest("233 S Wack")
        assert client.suggest("  233  s wack ") == first
        assert len(session.calls) == 1

    def test_an_empty_answer_is_cached_too(self):
        client, session, _ = make(results_handler())
        client.suggest("zzzz")
        client.suggest("zzzz")
        assert len(session.calls) == 1

    @pytest.mark.parametrize("body", [{}, {"results": None}, {"results": "x"}, "oops", None])
    def test_unreadable_answers(self, body):
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        with pytest.raises(RoutingUnavailable, match="cannot be read"):
            client.suggest("wacker")

    def test_a_400_means_no_matches(self):
        client, _, _ = make(lambda u, p: FakeResponse(400, {"detailedError": {}}))
        assert client.suggest("%%%%") == []

    def test_a_rejected_request_is_unavailable_and_never_shows_the_key(self):
        client, _, _ = make(lambda u, p: FakeResponse(403, {}))
        with pytest.raises(RoutingUnavailable, match="HTTP 403") as caught:
            client.suggest("wacker")
        assert KEY not in str(caught.value)


# -------------------------------------------------------------------------------- reverse


def reverse_body(label="217 South Wacker Drive, Chicago, IL 60606", country="US"):
    return {"addresses": [{"address": {"freeformAddress": label, "countryCode": country}, "position": "41.8789,-87.6359"}]}


class TestReverse:
    def test_the_address_at_a_position(self):
        client, _, _ = make(lambda u, p: FakeResponse(200, reverse_body()))
        place = client.reverse(41.878912345, -87.635912345)
        assert place == Place(query="41.87891,-87.63591", label="217 South Wacker Drive, Chicago, IL 60606", lat=41.87891, lon=-87.63591)

    def test_request_shape(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, reverse_body()))
        client.reverse(41.8789, -87.6359)
        [(url, params)] = session.calls
        assert url == f"{BASE_URL}/search/2/reverseGeocode/41.878900,-87.635900.json"
        assert params == {"radius": 1000, "key": KEY}

    def test_a_position_outside_the_us_is_refused(self):
        client, _, _ = make(lambda u, p: FakeResponse(200, reverse_body("Seoul-Jikhalsi", "KR")))
        with pytest.raises(LocationNotCovered):
            client.reverse(37.5665, 126.978)

    @pytest.mark.parametrize("body", [{"addresses": []}, reverse_body(label="")])
    def test_no_address_nearby_is_refused(self, body):
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        with pytest.raises(LocationNotCovered):
            client.reverse(41.5, -85.0)

    def test_a_missing_country_is_refused(self):
        body = {"addresses": [{"address": {"freeformAddress": "Somewhere"}}]}
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        with pytest.raises(LocationNotCovered):
            client.reverse(41.5, -85.0)

    @pytest.mark.parametrize("body", [{}, {"addresses": None}, {"addresses": [{}]}, {"addresses": ["x"]}, "oops", None])
    def test_unreadable_answers(self, body):
        client, _, _ = make(lambda u, p: FakeResponse(200, body))
        with pytest.raises(RoutingUnavailable, match="cannot be read"):
            client.reverse(41.5, -85.0)

    def test_a_repeat_nearby_is_served_from_the_cache(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, reverse_body()))
        client.reverse(41.87891, -87.63591)
        client.reverse(41.878912, -87.635908)  # the same to 4 decimals (about 10 m)
        assert len(session.calls) == 1

    def test_a_refusal_is_not_cached(self):
        client, session, _ = make(lambda u, p: FakeResponse(200, reverse_body("Seoul", "KR")))
        for _ in range(2):
            with pytest.raises(LocationNotCovered):
                client.reverse(37.5665, 126.978)
        assert len(session.calls) == 2

    def test_a_400_is_unavailable(self):
        client, _, _ = make(lambda u, p: FakeResponse(400, {}))
        with pytest.raises(RoutingUnavailable, match="HTTP 400"):
            client.reverse(41.5, -85.0)


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

    @pytest.mark.parametrize(
        "instructions, points",
        [
            ([(0, 0, 0), (1, 600, 101), (2, 1000, 100)], None),  # a turn a second after the arrival
            ([(0, 0, 0), (1, 1001, 60), (2, 1000, 100)], None),  # a turn a meter past the end
            ([(0, 0, 0), (7, 600, 60), (2, 1000, 100)], None),  # a point index past the line
            ([(0, 0, 0)], [(41.0, -87.0)]),                      # a single point
        ],
    )
    def test_a_route_that_checkpoints_cannot_be_built_from_is_refused_and_not_cached(self, instructions, points):
        broken = route_json(points or [(41.0, -87.0), (41.1, -87.1), (41.2, -87.2)], instructions)
        client, session, _ = make(routes_handler([ROUTE_A, broken]))
        for _ in range(2):
            with pytest.raises(RoutingUnavailable, match="not consistent"):
                client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert len(session.calls) == 2  # asked again: the broken answer was not kept

    def test_a_route_of_length_zero_is_passed_on(self):
        # The caller reports it as "the origin and the destination are the same place".
        same = route_json([(41.0, -87.0), (41.0, -87.0)], [(0, 0, 0), (1, 0, 0)], length=0, time=0)
        client, _, _ = make(routes_handler([same]))
        [route] = client.routes(CHICAGO, DENVER, DEPART, 1000)
        assert route.length_m == 0

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
