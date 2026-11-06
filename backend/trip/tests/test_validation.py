"""Tests for trip/validation.py and trip/errors.py (the error mapping)."""

from datetime import datetime, timedelta, timezone

import pytest

from trip.errors import DepartureInPast, InvalidInput, to_api_error
from trip.tomtom import GeocodeNotFound, LocationNotCovered, NoRoute, RoutingUnavailable
from trip.validation import (
    MAX_LOAD_WEIGHT_LB,
    PAST_GRACE,
    PickedPlace,
    parse_analyze_request,
    parse_place_query,
    parse_position,
)
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


class TestPickedPlaces:
    def place(self, **override):
        data = {"label": "Willis Tower, 233 South Wacker Drive, Chicago, IL", "lat": 41.8789, "lon": -87.6359}
        data.update(override)
        return {k: v for k, v in data.items() if v is not ...}

    def test_a_chosen_place_is_accepted_for_either_end(self):
        req = parse_analyze_request(body(origin=self.place(), destination=self.place(label=" Denver ", lat=39.7, lon=-105)), NOW)
        assert req.origin == PickedPlace("Willis Tower, 233 South Wacker Drive, Chicago, IL", 41.8789, -87.6359)
        assert req.destination == PickedPlace("Denver", 39.7, -105.0)  # trimmed, numbers as floats

    def test_text_and_a_chosen_place_can_be_mixed(self):
        req = parse_analyze_request(body(origin="Chicago, IL", destination=self.place()), NOW)
        assert req.origin == "Chicago, IL" and isinstance(req.destination, PickedPlace)

    @pytest.mark.parametrize(
        "lat, lon",
        [(25.76, -80.19), (47.61, -122.33), (44.8, -68.8), (19.7, -155.1), (61.2, -149.9), (71.3, -156.8), (18, -180), (72, -66)],
    )
    def test_places_in_the_united_states_are_allowed(self, lat, lon):
        # Miami, Seattle, Bangor, Hilo, Anchorage, Utqiagvik and the corners of the box
        assert parse_analyze_request(body(origin=self.place(lat=lat, lon=lon)), NOW).origin.lat == float(lat)

    @pytest.mark.parametrize(
        "lat, lon",
        [(51.5074, -0.1278), (0, 0), (-33.87, 151.21), (37.57, 126.98), (17.99, -100), (72.01, -100), (40, -65.99), (-16.8, 180), (90, 180), (-90, -180)],
    )
    def test_a_position_outside_the_united_states_is_refused(self, lat, lon):
        # London, the equator, Sydney, Seoul, just outside each side of the box, Fiji, the poles
        error = field_error(destination=self.place(lat=lat, lon=lon))
        assert error.field == "destination"
        assert "outside the United States" in error.message

    @pytest.mark.parametrize("name", ["lat", "lon"])
    def test_an_integer_too_large_for_a_float_is_refused_not_a_crash(self, name):
        assert field_error(origin=self.place(**{name: 10**400})).field == "origin"
        assert field_error(origin=self.place(**{name: -(10**400)})).field == "origin"

    @pytest.mark.parametrize("label", ["abc\ud800", "ab\x00cd", "a\x1bb", "x\x7f"])
    def test_a_label_with_characters_that_cannot_be_sent_on_is_refused(self, label):
        assert field_error(origin=self.place(label=label)).field == "origin"

    @pytest.mark.parametrize("override", [{"label": ""}, {"label": "  "}, {"label": 5}, {"label": None}, {"label": ...}, {"label": "x" * 201}])
    def test_a_bad_label_names_the_field(self, override):
        assert field_error(origin=self.place(**override)).field == "origin"

    @pytest.mark.parametrize("override", [{"lat": 90.1}, {"lat": -91}, {"lat": "41.8"}, {"lat": None}, {"lat": True}, {"lat": float("nan")}, {"lat": float("inf")}, {"lat": ...},
                                          {"lon": 180.1}, {"lon": -181}, {"lon": "x"}, {"lon": None}, {"lon": False}, {"lon": float("-inf")}, {"lon": ...}])
    def test_bad_coordinates_name_the_field(self, override):
        error = field_error(destination=self.place(**override))
        assert error.field == "destination"

    @pytest.mark.parametrize("value", [[], 5, True, None, ["Chicago"]])
    def test_other_types_are_not_a_place(self, value):
        assert field_error(origin=value).field == "origin"

    def test_an_empty_object_is_not_a_place(self):
        assert field_error(origin={}).field == "origin"


class TestHostileInput:
    """Valid JSON that used to end in an HTTP 500."""

    def test_a_load_weight_too_large_for_a_float(self):
        assert field_error(load_weight_lb=10**400).field == "load_weight_lb"
        assert field_error(load_weight_lb=-(10**400)).field == "load_weight_lb"

    @pytest.mark.parametrize(
        "departure",
        ["0001-01-01T00:00:00+05:00", "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-05:00", "9999-12-31T23:59:59-12:00"],
    )
    def test_a_departure_at_the_edge_of_the_calendar(self, departure):
        # Converting these to UTC leaves the years 1 to 9999.
        assert field_error(departure=departure).field == "departure"

    @pytest.mark.parametrize("text", ["abc\ud800", "\udfff Chicago", "Chi\x00cago", "Chicago\x1b[0m", "a\x7fb"])
    def test_control_characters_and_lone_surrogates_in_an_address(self, text):
        for field in ("origin", "destination"):
            error = field_error(**{field: text})
            assert error.field == field and "cannot be used" in error.message

    def test_a_pasted_line_break_or_tab_is_just_a_space(self):
        req = parse_analyze_request(body(origin="233 S Wacker Dr\n\tChicago,  IL\r\n"), NOW)
        assert req.origin == "233 S Wacker Dr Chicago, IL"

    @pytest.mark.parametrize("text", ["Zürich Rd, Lake Zurich, IL", "서울식당, Chicago", "Café 👩‍👩‍👧 Diner", "O'Hare / Terminal #5 (50%)"])
    def test_ordinary_text_in_any_script_is_kept(self, text):
        assert parse_analyze_request(body(origin=text), NOW).origin == text

    @pytest.mark.parametrize("q", ["abc\ud800", "ab\x00cd"])
    def test_a_search_text_with_such_characters_is_refused(self, q):
        with pytest.raises(InvalidInput):
            parse_place_query({"q": q})


class TestPlaceQueryParams:
    def test_a_search_text_is_trimmed_and_squeezed(self):
        assert parse_place_query({"q": "  233   S  Wack "}) == "233 S Wack"

    @pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}, {"q": None}, {"q": 5}, {"q": "x" * 201}])
    def test_a_missing_or_bad_text_is_refused(self, params):
        with pytest.raises(InvalidInput):
            parse_place_query(params)

    def test_a_position(self):
        assert parse_position({"lat": "41.8789", "lon": "-87.6359"}) == (41.8789, -87.6359)

    @pytest.mark.parametrize(
        "params",
        [{}, {"lat": "41"}, {"lon": "-87"}, {"lat": "x", "lon": "1"}, {"lat": "", "lon": "1"}, {"lat": "91", "lon": "0"}, {"lat": "0", "lon": "-181"}, {"lat": "nan", "lon": "0"}, {"lat": "inf", "lon": "0"}, {"lat": None, "lon": "0"}],
    )
    def test_a_bad_position_is_refused(self, params):
        with pytest.raises(InvalidInput):
            parse_position(params)


class TestLocationNotCoveredError:
    def test_it_is_a_422_that_says_the_us_only(self):
        status, body = to_api_error(LocationNotCovered("position is in KR"))
        assert status == 422 and body["error"]["code"] == "GEOCODE_NOT_FOUND"
        assert "United States" in body["error"]["message"] and "KR" not in body["error"]["message"]
