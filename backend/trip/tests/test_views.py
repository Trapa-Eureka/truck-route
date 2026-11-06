"""HTTP-level tests of POST /api/analyze (Django test client, fake services)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from trip import views
from trip.tests.helpers import FakeRouting, FakeWeather, recorded_route
from trip.tomtom import LocationNotCovered, NoRoute, Place, RoutingUnavailable, Suggestion
from trip.weather import ForecastOutOfRange, WeatherUnavailable

URL = "/api/analyze"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def services(monkeypatch):
    routing = FakeRouting([recorded_route(), recorded_route(time_factor=1.2), recorded_route(time_factor=1.5)])
    weather = FakeWeather()
    monkeypatch.setattr(views, "get_tomtom", lambda: routing)
    monkeypatch.setattr(views, "get_weather", lambda: weather)
    return routing, weather


def payload(**override):
    data = {
        "origin": "Chicago, IL",
        "destination": "Madison, WI",
        "departure": (timezone.now() + timedelta(days=2)).isoformat(),
        "load_weight_lb": 42000,
        "interval_miles": 25,
    }
    data.update(override)
    return data


def post(client, data, **kwargs):
    return client.post(URL, data, format="json", **kwargs)


class TestSuccess:
    def test_200_with_the_analysis(self, client, services):
        response = post(client, payload())
        assert response.status_code == 200
        body = response.json()
        assert [r["id"] for r in body["routes"]] == ["A", "B", "C"]
        assert body["recommendation"]["route_id"] == "A"

    def test_the_content_type_is_json(self, client, services):
        assert post(client, payload())["Content-Type"].startswith("application/json")

    def test_the_request_reaches_the_services(self, client, services):
        routing, weather = services
        post(client, payload(load_weight_lb=55000, interval_miles=10))
        assert routing.route_calls[0][3] == 55000.0
        assert len(weather.calls) == 1

    def test_a_departure_a_minute_ago_is_accepted(self, client, services):
        data = payload(departure=(timezone.now() - timedelta(minutes=1)).isoformat())
        assert post(client, data).status_code == 200

    def test_no_trailing_slash_is_needed_or_wanted(self, client, services):
        assert post(client, payload()).status_code == 200


class TestValidationErrors:
    @pytest.mark.parametrize(
        "override, field",
        [
            ({"origin": ""}, "origin"),
            ({"destination": None}, "destination"),
            ({"departure": "tomorrow"}, "departure"),
            ({"departure": "2026-11-09T14:00:00"}, "departure"),
            ({"load_weight_lb": "heavy"}, "load_weight_lb"),
            ({"load_weight_lb": -1}, "load_weight_lb"),
            ({"interval_miles": 30}, "interval_miles"),
        ],
    )
    def test_400_invalid_input_with_the_field(self, client, services, override, field):
        response = post(client, payload(**override))
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "INVALID_INPUT" and error["field"] == field and error["message"]

    def test_departure_in_the_past(self, client, services):
        response = post(client, payload(departure=(timezone.now() - timedelta(days=1)).isoformat()))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "DEPARTURE_IN_PAST"

    def test_validation_happens_before_any_service_is_used(self, client, monkeypatch):
        def boom():
            raise AssertionError("a service was created for an invalid request")

        monkeypatch.setattr(views, "get_tomtom", boom)
        monkeypatch.setattr(views, "get_weather", boom)
        assert post(client, payload(interval_miles=7)).status_code == 400

    def test_a_body_that_is_not_json(self, client, services):
        response = client.post(URL, "{oops", content_type="application/json")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_INPUT"

    def test_a_json_array(self, client, services):
        response = post(client, [1, 2, 3])
        assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_INPUT"

    def test_an_empty_body(self, client, services):
        response = client.post(URL, "", content_type="application/json")
        assert response.status_code == 400

    def test_get_is_not_allowed(self, client, services):
        response = client.get(URL)
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "INVALID_INPUT"

    def test_the_same_place(self, client, services):
        response = post(client, payload(destination="Chicago, IL"))
        assert response.status_code == 400
        assert response.json()["error"]["field"] == "destination"


class TestServiceErrors:
    def test_unknown_address_is_422_with_the_field(self, client, services):
        response = post(client, payload(origin="Atlantis"))
        assert response.status_code == 422
        error = response.json()["error"]
        assert (error["code"], error["field"]) == ("GEOCODE_NOT_FOUND", "origin")
        assert "Atlantis" in error["message"]

    def test_no_route_is_422(self, client, monkeypatch):
        class NoRouteRouting(FakeRouting):
            def routes(self, *args):
                raise NoRoute("none")

        monkeypatch.setattr(views, "get_tomtom", lambda: NoRouteRouting([]))
        monkeypatch.setattr(views, "get_weather", lambda: FakeWeather())
        response = post(client, payload())
        assert response.status_code == 422 and response.json()["error"]["code"] == "NO_ROUTE"

    def test_forecast_out_of_range_is_422_with_forecast_end(self, client, services, monkeypatch):
        from datetime import datetime, timezone as tz

        class Failing:
            def get_weather_at(self, queries):
                raise ForecastOutOfRange("x", forecast_end=datetime(2026, 11, 21, 18, tzinfo=tz.utc))

        monkeypatch.setattr(views, "get_weather", lambda: Failing())
        response = post(client, payload())
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "FORECAST_OUT_OF_RANGE" and error["forecast_end"] == "2026-11-21T18:00:00Z"

    @pytest.mark.parametrize("exc, code", [(WeatherUnavailable("down"), "WEATHER_UNAVAILABLE")])
    def test_weather_outage_is_502(self, client, services, monkeypatch, exc, code):
        class Failing:
            def get_weather_at(self, queries):
                raise exc

        monkeypatch.setattr(views, "get_weather", lambda: Failing())
        response = post(client, payload())
        assert response.status_code == 502 and response.json()["error"]["code"] == code

    def test_routing_outage_is_502(self, client, monkeypatch):
        class Down(FakeRouting):
            def geocode(self, query):
                raise RoutingUnavailable("TomTom is not responding (HTTP 503).")

        monkeypatch.setattr(views, "get_tomtom", lambda: Down([]))
        monkeypatch.setattr(views, "get_weather", lambda: FakeWeather())
        response = post(client, payload())
        assert response.status_code == 502
        error = response.json()["error"]
        assert error["code"] == "ROUTING_UNAVAILABLE" and "503" not in error["message"]

    def test_every_error_has_the_one_shape(self, client, services):
        bodies = [
            post(client, payload(origin="")).json(),
            post(client, payload(origin="Atlantis")).json(),
            post(client, payload(departure=(timezone.now() - timedelta(days=1)).isoformat())).json(),
            client.get(URL).json(),
        ]
        for body in bodies:
            assert set(body) == {"error"}
            assert {"code", "message"} <= set(body["error"])


class TestSettings:
    def test_the_missing_tomtom_key_is_a_server_configuration_error(self, monkeypatch, settings):
        from django.core.exceptions import ImproperlyConfigured

        from trip import services as services_module

        monkeypatch.setattr(services_module, "_tomtom", None)
        settings.TOMTOM_API_KEY = ""
        with pytest.raises(ImproperlyConfigured):
            services_module.get_tomtom()

    def test_the_tomtom_client_is_created_once(self, monkeypatch, settings):
        from trip import services as services_module

        monkeypatch.setattr(services_module, "_tomtom", None)
        settings.TOMTOM_API_KEY = "k"
        assert services_module.get_tomtom() is services_module.get_tomtom()


class TestHeatmapView:
    URL = "/api/heatmap"

    def test_200_with_the_grid(self, client, services):
        response = client.post(self.URL, payload(), format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["hours"] == 49 and len(body["scores"]) == 49
        assert len(body["scores"][0]) == len(body["points"])

    def test_the_same_body_as_analyze(self, client, services):
        data = payload()
        assert client.post(URL, data, format="json").status_code == 200
        assert client.post(self.URL, data, format="json").status_code == 200

    def test_validation_errors_use_the_same_shape(self, client, services):
        response = client.post(self.URL, payload(interval_miles=30), format="json")
        assert response.status_code == 400
        assert response.json()["error"]["field"] == "interval_miles"

    def test_validation_happens_before_any_service_is_used(self, client, monkeypatch):
        def boom():
            raise AssertionError("a service was created for an invalid request")

        monkeypatch.setattr(views, "get_tomtom", boom)
        monkeypatch.setattr(views, "get_weather", boom)
        assert client.post(self.URL, payload(origin=""), format="json").status_code == 400

    def test_forecast_out_of_range_is_422_with_the_end(self, client, services, monkeypatch):
        from datetime import datetime, timezone as tz

        class Failing:
            def get_weather_at(self, queries):
                raise ForecastOutOfRange("x", forecast_end=datetime(2026, 11, 21, 18, tzinfo=tz.utc))

        monkeypatch.setattr(views, "get_weather", lambda: Failing())
        response = client.post(self.URL, payload(), format="json")
        assert response.status_code == 422
        assert response.json()["error"]["forecast_end"] == "2026-11-21T18:00:00Z"

    def test_weather_outage_is_502(self, client, services, monkeypatch):
        class Failing:
            def get_weather_at(self, queries):
                raise WeatherUnavailable("down")

        monkeypatch.setattr(views, "get_weather", lambda: Failing())
        assert client.post(self.URL, payload(), format="json").status_code == 502

    def test_get_is_not_allowed(self, client, services):
        assert client.get(self.URL).status_code == 405


class TestCompression:
    def test_a_large_answer_is_gzipped_when_the_browser_accepts_it(self, client, services):
        import gzip

        response = client.post(URL, payload(), format="json", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
        assert response["Content-Encoding"] == "gzip"
        assert response["Vary"] == "Accept-Encoding"
        body = gzip.decompress(response.content)
        assert b'"recommendation"' in body
        assert len(response.content) < len(body) / 3  # JSON of this shape compresses well

    def test_it_is_not_compressed_for_a_client_that_does_not_ask(self, client, services):
        response = client.post(URL, payload(), format="json")
        assert "Content-Encoding" not in response
        assert response.json()["recommendation"]["route_id"] == "A"

    def test_the_heatmap_is_gzipped_too(self, client, services):
        response = client.post("/api/heatmap", payload(), format="json", headers={"Accept-Encoding": "gzip"})
        assert response["Content-Encoding"] == "gzip"


def suggestion(**override):
    data = dict(id="p1", kind="place", name="Willis Tower", detail="233 South Wacker Drive, Chicago, IL 60606",
                label="Willis Tower, 233 South Wacker Drive, Chicago, IL 60606", lat=41.878881234, lon=-87.635912345)
    data.update(override)
    return Suggestion(**data)


@pytest.fixture
def places(monkeypatch):
    routing = FakeRouting([])
    routing.suggestions = [suggestion(), suggestion(id="a1", kind="address", name="233 South Wacker Drive", detail="Chicago, IL 60606", label="233 South Wacker Drive, Chicago, IL 60606")]
    routing.reverse_result = Place("41.87891,-87.63591", "217 South Wacker Drive, Chicago, IL 60606", 41.87891, -87.63591)
    monkeypatch.setattr(views, "get_tomtom", lambda: routing)
    return routing


class TestPlaces:
    URL = "/api/places"

    def test_the_choices_for_a_text(self, client, places):
        response = client.get(self.URL, {"q": " willis  tow "})
        assert response.status_code == 200
        body = response.json()
        assert [i["id"] for i in body["suggestions"]] == ["p1", "a1"]
        assert body["suggestions"][0] == {
            "id": "p1", "kind": "place", "name": "Willis Tower", "detail": "233 South Wacker Drive, Chicago, IL 60606",
            "label": "Willis Tower, 233 South Wacker Drive, Chicago, IL 60606", "lat": 41.87888, "lon": -87.63591,
        }
        assert places.suggested == ["willis tow"]  # trimmed and squeezed before the search

    def test_no_choices_is_an_empty_list_not_an_error(self, client, places):
        places.suggestions = []
        response = client.get(self.URL, {"q": "zzzz"})
        assert response.status_code == 200 and response.json() == {"suggestions": []}

    @pytest.mark.parametrize("query", [{}, {"q": ""}, {"q": "   "}, {"q": "x" * 201}])
    def test_a_missing_or_bad_text_is_a_400(self, client, places, query):
        response = client.get(self.URL, query)
        assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_INPUT"
        assert not hasattr(places, "suggested")

    def test_a_search_outage_is_502_without_details(self, client, monkeypatch):
        class Down(FakeRouting):
            def suggest(self, query):
                raise RoutingUnavailable("TomTom is not responding (HTTP 503).")

        monkeypatch.setattr(views, "get_tomtom", lambda: Down([]))
        response = client.get(self.URL, {"q": "wacker"})
        assert response.status_code == 502
        error = response.json()["error"]
        assert error["code"] == "ROUTING_UNAVAILABLE" and "503" not in error["message"]

    def test_post_is_not_allowed(self, client, places):
        assert client.post(self.URL, {"q": "wacker"}, format="json").status_code == 405


class TestReversePlace:
    URL = "/api/places/reverse"

    def test_the_address_at_a_position(self, client, places):
        response = client.get(self.URL, {"lat": "41.8789", "lon": "-87.6359"})
        assert response.status_code == 200
        assert response.json() == {"place": {"label": "217 South Wacker Drive, Chicago, IL 60606", "lat": 41.87891, "lon": -87.63591}}
        assert places.reversed == [(41.8789, -87.6359)]

    @pytest.mark.parametrize("query", [{}, {"lat": "41"}, {"lat": "x", "lon": "1"}, {"lat": "95", "lon": "0"}, {"lat": "0", "lon": "200"}])
    def test_a_bad_position_is_a_400(self, client, places, query):
        response = client.get(self.URL, query)
        assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_INPUT"
        assert not hasattr(places, "reversed")

    def test_outside_the_us_is_a_422_that_says_so(self, client, monkeypatch):
        class Abroad(FakeRouting):
            def reverse(self, lat, lon):
                raise LocationNotCovered("position is in KR")

        monkeypatch.setattr(views, "get_tomtom", lambda: Abroad([]))
        response = client.get(self.URL, {"lat": "37.5665", "lon": "126.978"})
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "GEOCODE_NOT_FOUND" and "United States" in error["message"]


class TestChosenPlaces:
    """A place picked from the list goes straight to routing: no address lookup, same answer."""

    def chosen(self, label, lat, lon):
        return {"label": label, "lat": lat, "lon": lon}

    def test_chosen_places_are_not_looked_up_again(self, client, services):
        routing, _ = services
        response = post(client, payload(origin=self.chosen("Willis Tower, Chicago", 41.8789, -87.6359), destination=self.chosen("Capitol, Madison", 43.0747, -89.3842)))
        assert response.status_code == 200
        assert routing.geocoded == []
        origin, destination = routing.route_calls[0][:2]
        assert (origin.lat, origin.lon) == (41.8789, -87.6359) and (destination.lat, destination.lon) == (43.0747, -89.3842)
        body = response.json()
        assert body["origin"]["label"] == "Willis Tower, Chicago" and body["destination"]["label"] == "Capitol, Madison"

    def test_text_is_still_looked_up(self, client, services):
        routing, _ = services
        post(client, payload(origin=self.chosen("Willis Tower, Chicago", 41.8789, -87.6359)))
        assert routing.geocoded == ["Madison, WI"]  # only the typed end

    def test_the_same_chosen_place_twice_is_refused(self, client, services):
        same = self.chosen("Willis Tower", 41.8789, -87.6359)
        response = post(client, payload(origin=same, destination=same))
        assert response.status_code == 400
        assert response.json()["error"]["field"] == "destination"

    def test_a_bad_chosen_place_names_its_field(self, client, services):
        response = post(client, payload(origin=self.chosen("Willis Tower", 99, -87.6)))
        assert response.status_code == 400 and response.json()["error"]["field"] == "origin"

    def test_the_heatmap_takes_chosen_places_too(self, client, services):
        routing, _ = services
        response = client.post("/api/heatmap", payload(origin=self.chosen("Willis Tower", 41.8789, -87.6359)), format="json")
        assert response.status_code == 200
        assert routing.geocoded == ["Madison, WI"]


# ------------------------------------------------------------- errors always in the contract shape


def error_of(response):
    assert response["Content-Type"].startswith("application/json"), response.content[:80]
    return response.json()["error"]


class TestNeverAnHtmlPage:
    """Inputs and failures that used to end in an HTML error page."""

    def raw(self, client, body, url=URL):
        return client.post(url, data=body, content_type="application/json")

    @pytest.mark.parametrize("url", [URL, "/api/heatmap"])
    def test_a_400_digit_load_weight(self, client, services, url):
        body = '{"origin":"Chicago, IL","destination":"Madison, WI","departure":"2099-01-01T00:00:00Z","load_weight_lb":1' + "0" * 400 + ',"interval_miles":25}'
        response = self.raw(client, body, url)
        assert response.status_code == 400
        assert error_of(response)["code"] == "INVALID_INPUT" and error_of(response)["field"] == "load_weight_lb"

    def test_a_400_digit_latitude(self, client, services):
        body = '{"origin":{"label":"x","lat":1' + "0" * 400 + ',"lon":-87.6},"destination":"Madison, WI","departure":"2099-01-01T00:00:00Z","load_weight_lb":1,"interval_miles":25}'
        response = self.raw(client, body)
        assert response.status_code == 400 and error_of(response)["field"] == "origin"

    @pytest.mark.parametrize("departure", ["0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-05:00"])
    def test_a_departure_at_the_edge_of_the_calendar(self, client, services, departure):
        response = post(client, payload(departure=departure))
        assert response.status_code == 400 and error_of(response)["field"] == "departure"

    def test_a_hundred_thousand_nested_brackets(self, client, services):
        response = self.raw(client, "[" * 100_000)
        assert response.status_code == 400
        assert error_of(response) == {"code": "INVALID_INPUT", "message": "The request body is not valid JSON."}

    def test_a_lone_surrogate_in_an_address(self, client, services):
        response = self.raw(client, '{"origin":"abc\\ud800","destination":"Madison, WI","departure":"2099-01-01T00:00:00Z","load_weight_lb":1,"interval_miles":25}')
        assert response.status_code == 400 and error_of(response)["field"] == "origin"

    def test_a_lone_surrogate_in_a_chosen_label_is_refused_before_any_service_is_used(self, client, services):
        routing, weather = services
        body = '{"origin":{"label":"abc\\ud800","lat":41.88,"lon":-87.63},"destination":"Madison, WI","departure":"2099-01-01T00:00:00Z","load_weight_lb":1,"interval_miles":25}'
        response = self.raw(client, body)
        assert response.status_code == 400 and error_of(response)["field"] == "origin"
        assert routing.route_calls == [] and weather.calls == []

    def test_the_parse_error_says_nothing_about_the_server(self, client, services):
        response = self.raw(client, '{"load_weight_lb": ' + "9" * 5000 + "}")
        assert response.status_code == 400
        message = error_of(response)["message"]
        assert "sys." not in message and "digits" not in message

    def test_a_body_over_the_size_limit(self, client, services):
        response = self.raw(client, '{"origin": "' + "x" * 3_000_000 + '"}')
        assert response.status_code == 400
        assert error_of(response) == {"code": "INVALID_INPUT", "message": "The request body is too large."}

    @pytest.mark.parametrize("url", [URL, "/api/heatmap"])
    def test_an_unexpected_failure_is_a_500_in_the_error_shape(self, client, services, monkeypatch, url):
        def broken(*args):
            raise RuntimeError("boom with a secret: SECRET-KEY-123")

        monkeypatch.setattr(views, "get_tomtom", broken)
        response = client.post(url, payload(), format="json")
        assert response.status_code == 500
        assert error_of(response) == {"code": "INTERNAL_ERROR", "message": "Something went wrong on our side. Please try again."}
        assert b"SECRET" not in response.content and b"boom" not in response.content

    def test_an_unexpected_failure_is_logged_with_its_traceback(self, client, services, monkeypatch, caplog):
        import logging

        def broken(*args):
            raise RuntimeError("boom")

        monkeypatch.setattr(views, "get_tomtom", broken)
        with caplog.at_level(logging.ERROR, logger="trip"):
            post(client, payload())
        [record] = [r for r in caplog.records if r.name == "trip.errors" and r.levelno == logging.ERROR]
        assert record.exc_info is not None and "AnalyzeView" in record.getMessage()

    def test_a_route_tomtom_got_wrong_is_a_502_not_a_500(self, client, services, monkeypatch):
        routing, _ = services

        def refuse(*args):
            raise RoutingUnavailable("TomTom sent a route that is not consistent.")

        monkeypatch.setattr(routing, "routes", refuse)
        response = post(client, payload())
        assert response.status_code == 502 and error_of(response)["code"] == "ROUTING_UNAVAILABLE"

    @pytest.mark.parametrize("path", ["/api/nothing", "/api/analyze/", "/", "/admin/", "/api/places/reverse/x"])
    def test_an_unknown_address_is_a_json_404(self, client, path):
        for response in (client.get(path), client.post(path, {}, format="json")):
            assert response.status_code == 404
            assert error_of(response) == {"code": "NOT_FOUND", "message": "There is nothing at this address."}

    def test_format_is_an_ordinary_unknown_parameter(self, client, places):
        places.suggestions = [suggestion()]
        assert client.get("/api/places", {"q": "wacker", "format": "xml"}).status_code == 200
        assert client.post(URL + "?format=xml", payload(origin=""), format="json").status_code == 400

    def test_a_wrong_host_is_refused_in_the_error_shape(self, client, services):
        response = client.post(URL, payload(), format="json", headers={"Host": "evil.example"})
        assert response.status_code == 400 and error_of(response)["code"] == "INVALID_INPUT"


# ----------------------------------------------------------------------------- request limits


class TestErrorHandlersDirectly:
    """Parts of trip/errors.py that a request through the test client does not reach exactly."""

    def test_the_wait_is_rounded_up_to_whole_seconds(self):
        from rest_framework.exceptions import Throttled

        from trip.errors import api_exception_handler

        # Waiting 12 seconds when 12.3 are needed would be refused again.
        response = api_exception_handler(Throttled(wait=12.3), {"view": None})
        assert response.status_code == 429
        assert response.data["error"]["retry_after_seconds"] == 13
        assert response.data["error"]["message"] == "Too many requests. Please try again in 13 seconds."

    def test_a_refusal_without_a_known_wait_still_has_a_message(self):
        from rest_framework.exceptions import Throttled

        from trip.errors import api_exception_handler

        error = api_exception_handler(Throttled(), {"view": None}).data["error"]
        assert error == {"code": "RATE_LIMITED", "message": "Too many requests. Please wait a moment and try again."}

    def test_the_handlers_for_errors_outside_the_api_views_answer_in_json(self):
        import json

        from trip import errors

        for handler, args, status, code in [
            (errors.server_error, (None,), 500, "INTERNAL_ERROR"),
            (errors.not_found, (None, None), 404, "NOT_FOUND"),
            (errors.bad_request, (None, None), 400, "INVALID_INPUT"),
        ]:
            response = handler(*args)
            assert response.status_code == status
            assert response["Content-Type"] == "application/json"
            body = json.loads(response.content)
            assert body["error"]["code"] == code and body["error"]["message"]

    def test_django_uses_them(self):
        from config import urls

        assert urls.handler400 == "trip.errors.bad_request"
        assert urls.handler404 == "trip.errors.not_found"
        assert urls.handler500 == "trip.errors.server_error"


class TestRequestLimits:
    """Per client address (trip/throttling.py); the counters start empty for every test."""

    def limit(self, settings, **rates):
        settings.RATE_LIMITS = {"trip_minute": None, "trip_day": None, "places_minute": None, "places_day": None, **rates}

    def test_the_request_after_the_limit_is_refused(self, client, services, settings):
        self.limit(settings, trip_minute="3/min")
        assert [post(client, payload()).status_code for _ in range(5)] == [200, 200, 200, 429, 429]

    def test_the_refusal_is_in_the_error_shape_and_says_how_long_to_wait(self, client, services, settings):
        self.limit(settings, trip_minute="1/min")
        post(client, payload())
        response = post(client, payload())
        error = error_of(response)
        assert error["code"] == "RATE_LIMITED"
        assert 1 <= error["retry_after_seconds"] <= 60
        assert f"in {error['retry_after_seconds']} seconds" in error["message"]
        assert response["Retry-After"] == str(error["retry_after_seconds"])

    def test_a_refused_request_uses_no_service(self, client, services, settings):
        routing, weather = services
        self.limit(settings, trip_minute="1/min")
        post(client, payload())
        post(client, payload())
        assert len(routing.route_calls) == 1 and len(weather.calls) == 1

    def test_the_analysis_and_the_heatmap_share_one_limit(self, client, services, settings):
        self.limit(settings, trip_minute="2/min")
        assert post(client, payload()).status_code == 200
        assert client.post("/api/heatmap", payload(), format="json").status_code == 200
        assert post(client, payload()).status_code == 429
        assert client.post("/api/heatmap", payload(), format="json").status_code == 429

    def test_the_daily_limit_applies_too(self, client, services, settings):
        self.limit(settings, trip_minute="100/min", trip_day="2/day")
        assert [post(client, payload()).status_code for _ in range(3)] == [200, 200, 429]

    def test_invalid_requests_count_as_well(self, client, services, settings):
        self.limit(settings, trip_minute="2/min")
        statuses = [post(client, payload(origin="")).status_code for _ in range(3)]
        assert statuses == [400, 400, 429]

    def test_place_search_and_my_location_share_a_limit(self, client, places, settings):
        self.limit(settings, places_minute="2/min")
        assert client.get("/api/places", {"q": "wacker"}).status_code == 200
        assert client.get("/api/places/reverse", {"lat": "41.8789", "lon": "-87.6359"}).status_code == 200
        response = client.get("/api/places", {"q": "wacker"})
        assert response.status_code == 429 and error_of(response)["code"] == "RATE_LIMITED"
        assert client.get("/api/places/reverse", {"lat": "41.8789", "lon": "-87.6359"}).status_code == 429

    def test_place_searches_do_not_use_up_the_trip_limit(self, client, services, settings):
        self.limit(settings, trip_minute="1/min", places_minute="1/min")
        client.get("/api/places", {"q": "wacker"})
        client.get("/api/places", {"q": "wacker"})
        assert post(client, payload()).status_code == 200

    def test_each_client_address_is_counted_on_its_own(self, client, services, settings):
        self.limit(settings, trip_minute="1/min")
        assert post(client, payload(), REMOTE_ADDR="10.0.0.1").status_code == 200
        assert post(client, payload(), REMOTE_ADDR="10.0.0.1").status_code == 429
        assert post(client, payload(), REMOTE_ADDR="10.0.0.2").status_code == 200

    def test_the_default_limits_are_set_for_all_four_scopes(self, settings):
        from rest_framework.throttling import SimpleRateThrottle

        assert set(settings.RATE_LIMITS) == {"trip_minute", "trip_day", "places_minute", "places_day"}
        for rate in settings.RATE_LIMITS.values():
            number, seconds = SimpleRateThrottle.parse_rate(None, rate)
            assert number > 0 and seconds in (60, 86400)

    def test_every_endpoint_has_a_limit(self):
        for view in (views.AnalyzeView, views.HeatmapView, views.PlacesView, views.ReversePlaceView):
            assert len(view.throttle_classes) == 2
