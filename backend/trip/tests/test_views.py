"""HTTP-level tests of POST /api/analyze (Django test client, fake services)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from trip import views
from trip.tests.helpers import FakeRouting, FakeWeather, recorded_route
from trip.tomtom import NoRoute, RoutingUnavailable
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
