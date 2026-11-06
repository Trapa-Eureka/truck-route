"""Tests for trip/validation.py and trip/errors.py (the error mapping)."""

from datetime import datetime, timedelta, timezone

import pytest

from trip.errors import DepartureInPast, InvalidInput, to_api_error
from trip.tomtom import GeocodeNotFound, NoRoute, RoutingUnavailable
from trip.validation import MAX_LOAD_WEIGHT_LB, PAST_GRACE, parse_analyze_request
from trip.weather import ForecastOutOfRange, WeatherUnavailable

UTC = timezone.utc
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def body(**override):
    data = {
        "origin": "Chicago, IL",
        "destination": "Denver, CO",
        "departure": "2026-11-09T14:00:00Z",
        "load_weight_lb": 42000,
        "interval_miles": 25,
    }
    data.update(override)
    return {k: v for k, v in data.items() if v is not ...}


def field_error(**override):
    with pytest.raises(InvalidInput) as caught:
        parse_analyze_request(body(**override), NOW)
    return caught.value


class TestValidRequests:
    def test_a_complete_request(self):
        req = parse_analyze_request(body(), NOW)
        assert (req.origin, req.destination) == ("Chicago, IL", "Denver, CO")
        assert req.departure == datetime(2026, 11, 9, 14, tzinfo=UTC)
        assert req.load_weight_lb == 42000.0 and req.interval_miles == 25

    def test_addresses_are_trimmed(self):
        req = parse_analyze_request(body(origin="  Chicago, IL \n"), NOW)
        assert req.origin == "Chicago, IL"

    def test_departure_with_an_offset_becomes_utc(self):
        req = parse_analyze_request(body(departure="2026-11-09T23:00:00+09:00"), NOW)
        assert req.departure == datetime(2026, 11, 9, 14, tzinfo=UTC)
        assert req.departure.utcoffset() == timedelta(0)

    @pytest.mark.parametrize("interval", [10, 25, 50, 25.0])
    def test_allowed_intervals(self, interval):
        assert parse_analyze_request(body(interval_miles=interval), NOW).interval_miles == int(interval)

    @pytest.mark.parametrize("weight", [0, 0.0, 1, 80000, 80000.5, MAX_LOAD_WEIGHT_LB])
    def test_allowed_weights(self, weight):
        assert parse_analyze_request(body(load_weight_lb=weight), NOW).load_weight_lb == float(weight)

    def test_a_zero_load_is_allowed(self):
        assert parse_analyze_request(body(load_weight_lb=0), NOW).load_weight_lb == 0.0


class TestAddresses:
    @pytest.mark.parametrize("field", ["origin", "destination"])
    @pytest.mark.parametrize("value", [..., None, "", "   ", 5, ["x"], {"a": 1}])
    def test_missing_or_wrong_type(self, field, value):
        error = field_error(**{field: value})
        assert error.field == field

    def test_too_long(self):
        assert field_error(origin="x" * 201).field == "origin"

    def test_the_longest_allowed(self):
        assert parse_analyze_request(body(origin="x" * 200), NOW).origin == "x" * 200


class TestDeparture:
    @pytest.mark.parametrize("value", [..., None, 12345, "", "tomorrow", "2026-13-40T00:00:00Z", ["2026-11-09"]])
    def test_missing_or_not_a_date(self, value):
        assert field_error(departure=value).field == "departure"

    def test_a_time_zone_is_required(self):
        error = field_error(departure="2026-11-09T14:00:00")
        assert error.field == "departure" and "time zone" in error.message

    def test_a_date_without_a_time_has_no_zone(self):
        assert field_error(departure="2026-11-09").field == "departure"

    def test_the_past_is_rejected(self):
        with pytest.raises(DepartureInPast):
            parse_analyze_request(body(departure="2026-11-06T11:00:00Z"), NOW)

    def test_a_few_minutes_ago_is_allowed_for_a_form_that_says_now(self):
        req = parse_analyze_request(body(departure=(NOW - PAST_GRACE).isoformat()), NOW)
        assert req.departure == NOW - PAST_GRACE

    def test_just_beyond_the_grace_is_rejected(self):
        with pytest.raises(DepartureInPast):
            parse_analyze_request(body(departure=(NOW - PAST_GRACE - timedelta(seconds=1)).isoformat()), NOW)

    def test_now_and_the_future_are_allowed(self):
        parse_analyze_request(body(departure=NOW.isoformat()), NOW)
        parse_analyze_request(body(departure="2026-11-20T00:00:00Z"), NOW)

    def test_no_upper_limit_a_few_weeks_out(self):
        # the forecast decides this later (FORECAST_OUT_OF_RANGE), not an arbitrary limit here
        parse_analyze_request(body(departure="2027-06-01T00:00:00Z"), NOW)

    def test_absurdly_far_dates_are_refused_before_date_maths_overflows(self):
        assert field_error(departure="9999-12-31T23:59:59Z").field == "departure"


class TestLoadWeight:
    @pytest.mark.parametrize("value", [..., None, "42000", True, False, [1], float("nan"), float("inf")])
    def test_missing_or_not_a_number(self, value):
        assert field_error(load_weight_lb=value).field == "load_weight_lb"

    def test_negative(self):
        assert field_error(load_weight_lb=-0.5).field == "load_weight_lb"

    def test_too_large(self):
        assert field_error(load_weight_lb=MAX_LOAD_WEIGHT_LB + 1).field == "load_weight_lb"


class TestInterval:
    @pytest.mark.parametrize("value", [..., None, 0, 5, 30, 100, -25, "25", True, 25.5, float("nan")])
    def test_only_10_25_50(self, value):
        assert field_error(interval_miles=value).field == "interval_miles"


class TestBody:
    @pytest.mark.parametrize("data", [None, [], [1, 2], "text", 5])
    def test_must_be_an_object(self, data):
        with pytest.raises(InvalidInput) as caught:
            parse_analyze_request(data, NOW)
        assert caught.value.field is None


class TestErrorMapping:
    def test_invalid_input(self):
        assert to_api_error(InvalidInput("Enter the origin.", "origin")) == (
            400, {"error": {"code": "INVALID_INPUT", "message": "Enter the origin.", "field": "origin"}},
        )

    def test_invalid_input_without_a_field_has_no_field_key(self):
        _, body_ = to_api_error(InvalidInput("bad body"))
        assert "field" not in body_["error"]

    def test_departure_in_past(self):
        status, body_ = to_api_error(DepartureInPast())
        assert status == 400 and body_["error"]["code"] == "DEPARTURE_IN_PAST"
        assert body_["error"]["field"] == "departure"

    def test_geocode_not_found(self):
        status, body_ = to_api_error(GeocodeNotFound("Nowhere", field="origin"))
        assert status == 422
        assert body_["error"]["code"] == "GEOCODE_NOT_FOUND" and body_["error"]["field"] == "origin"
        assert "Nowhere" in body_["error"]["message"]

    def test_no_route(self):
        status, body_ = to_api_error(NoRoute("x"))
        assert status == 422 and body_["error"]["code"] == "NO_ROUTE"

    def test_forecast_out_of_range_with_the_end(self):
        exc = ForecastOutOfRange("x", forecast_end=datetime(2026, 11, 21, 18, tzinfo=UTC))
        status, body_ = to_api_error(exc)
        assert status == 422
        assert body_["error"]["code"] == "FORECAST_OUT_OF_RANGE"
        assert body_["error"]["forecast_end"] == "2026-11-21T18:00:00Z"
        assert "Nov 21, 18:00 UTC" in body_["error"]["message"]

    def test_forecast_out_of_range_without_the_end(self):
        status, body_ = to_api_error(ForecastOutOfRange("x"))
        assert status == 422 and "forecast_end" not in body_["error"]

    def test_forecast_end_in_another_zone_is_reported_in_utc(self):
        seoul = timezone(timedelta(hours=9))
        exc = ForecastOutOfRange("x", forecast_end=datetime(2026, 11, 22, 3, tzinfo=seoul))
        assert to_api_error(exc)[1]["error"]["forecast_end"] == "2026-11-21T18:00:00Z"

    def test_routing_and_weather_outages_are_502_and_hide_details(self):
        for exc, code in [(RoutingUnavailable("secret detail"), "ROUTING_UNAVAILABLE"), (WeatherUnavailable("secret detail"), "WEATHER_UNAVAILABLE")]:
            status, body_ = to_api_error(exc)
            assert status == 502 and body_["error"]["code"] == code
            assert "secret" not in body_["error"]["message"]

    def test_other_exceptions_are_not_mapped(self):
        assert to_api_error(ValueError("x")) is None
        assert to_api_error(KeyError("x")) is None
