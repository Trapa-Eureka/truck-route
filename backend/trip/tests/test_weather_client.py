"""Tests for trip/weather_client.py with a fake HTTP session (no network)."""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from trip import weather_client
from trip.weather import ForecastOutOfRange, WeatherSample, WeatherUnavailable
from trip.weather_client import MAX_LOCATIONS_PER_REQUEST, WeatherClient, WeatherQuery

UTC = timezone.utc
T0 = datetime(2026, 11, 9, 12, tzinfo=UTC)

UNITS = {
    "time": "iso8601",
    "wind_speed_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}


class FakeResponse:
    def __init__(self, status_code=200, body=None, not_json=False):
        self.status_code = status_code
        self._body = body
        self._not_json = not_json

    def json(self):
        if self._not_json:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """Answers ``get`` with ``handler(params)``; a handler may return an exception to raise."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, params, timeout):
        assert url == weather_client.OPEN_METEO_URL
        assert timeout == weather_client.REQUEST_TIMEOUT_SECONDS
        self.calls.append(params)
        result = self.handler(params)
        if isinstance(result, Exception):
            raise result
        return result


class DictCache:
    """Minimal stand-in for Django's cache (get_many / set_many)."""

    def __init__(self):
        self.data = {}
        self.set_calls = 0

    def get_many(self, keys):
        return {k: self.data[k] for k in keys if k in self.data}

    def set_many(self, data, timeout=None):
        self.set_calls += 1
        self.timeout = timeout
        self.data.update(data)


def hours_between(start, end):
    hour = datetime.strptime(start, "%Y-%m-%dT%H:%M")
    last = datetime.strptime(end, "%Y-%m-%dT%H:%M")
    while hour <= last:
        yield hour
        hour += timedelta(hours=1)


def body_for(params, value=None, null_from=None):
    """An Open-Meteo style answer for the request ``params``.

    ``value(lat, lon, hour)`` returns (wind, rain, showers, snow); by default the wind encodes the
    latitude and the hour so a test can tell answers apart. Hours from ``null_from`` on are null.
    """
    lats = [float(x) for x in params["latitude"].split(",")]
    lons = [float(x) for x in params["longitude"].split(",")]
    hours = list(hours_between(params["start_hour"], params["end_hour"]))

    def default(lat, lon, hour):
        return (lat + hour.hour / 100, 0.0, 0.0, 0.0)

    value = value or default
    entries = []
    for lat, lon in zip(lats, lons):
        columns = {"wind_speed_10m": [], "rain": [], "showers": [], "snowfall": []}
        for hour in hours:
            if null_from is not None and hour >= null_from:
                row = (None, None, None, None)
            else:
                row = value(lat, lon, hour)
            for name, number in zip(columns, row):
                columns[name].append(number)
        entries.append(
            {
                "hourly_units": UNITS,
                "hourly": {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours], **columns},
            }
        )
    return entries if len(entries) > 1 else entries[0]


def answering(value=None, null_from=None):
    return FakeSession(lambda params: FakeResponse(200, body_for(params, value, null_from)))


def make_client(session, cache=None, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return WeatherClient(session=session, cache=cache or DictCache(), sleep=sleeps.append), sleeps


def q(lat, lon, hours=0, minutes=0):
    return WeatherQuery(lat, lon, T0 + timedelta(hours=hours, minutes=minutes))


# ------------------------------------------------------------- which forecast hour is used


def hourly(lat, lon, hour):
    """Wind, rain, showers and snow that each encode the forecast hour they belong to."""
    return (hour.hour + 0.5, hour.hour / 100, 0.0, hour.hour / 10)


class TestWhichHour:
    """Wind: the nearest hour. Rain and snow: the hour whose sums cover the time."""

    @pytest.mark.parametrize(
        "minutes, wind_hour, rain_hour",
        [(0, 12, 12), (1, 12, 13), (29, 12, 13), (30, 13, 13), (59, 13, 13), (60, 13, 13), (61, 13, 14)],
    )
    def test_wind_and_rain_hours(self, minutes, wind_hour, rain_hour):
        client, _ = make_client(answering(value=hourly))
        [sample] = client.get_weather_at([q(40.0, -90.0, minutes=minutes)])
        assert sample == WeatherSample(wind_hour + 0.5, rain_hour / 100, rain_hour / 10)

    def test_a_storm_that_starts_on_the_hour_is_seen_by_a_truck_arriving_just_after(self):
        # 1.2 in/hr falls from 14:00 to 15:00: Open-Meteo stamps it 15:00.
        def storm(lat, lon, hour):
            return (5.0, 1.2 if hour.hour == 15 else 0.0, 0.0, 0.0)

        client, _ = make_client(answering(value=storm))
        times = [(2, 0), (2, 1), (2, 29), (2, 30), (2, 59), (3, 0), (3, 1)]  # after T0 = 12:00
        samples = client.get_weather_at([q(40.0, -90.0, hours=h, minutes=m) for h, m in times])
        assert [s.rain_in_hr for s in samples] == [0.0, 1.2, 1.2, 1.2, 1.2, 1.2, 0.0]

    def test_both_hours_are_asked_for_in_one_request(self):
        session = answering(value=hourly)
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0, minutes=10)])
        [params] = session.calls
        assert (params["start_hour"], params["end_hour"]) == ("2026-11-09T12:00", "2026-11-09T13:00")

    def test_a_time_on_the_hour_needs_one_hour_only(self):
        session = answering(value=hourly)
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0)])
        [params] = session.calls
        assert params["start_hour"] == params["end_hour"] == "2026-11-09T12:00"

    def test_the_second_hour_comes_from_the_cache_when_it_is_there(self):
        session = answering(value=hourly)
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0, minutes=40)])  # caches 13:00
        client.get_weather_at([q(40.0, -90.0, minutes=10)])  # needs 12:00 (new) and 13:00 (cached)
        assert len(session.calls) == 2
        assert session.calls[1]["start_hour"] == session.calls[1]["end_hour"] == "2026-11-09T12:00"

    def test_results_stay_in_query_order_with_mixed_hours(self):
        client, _ = make_client(answering(value=hourly))
        samples = client.get_weather_at(
            [q(40.0, -90.0, minutes=45), q(41.0, -91.0, minutes=10), q(40.0, -90.0, minutes=10)]
        )
        assert [(s.wind_mph, s.rain_in_hr) for s in samples] == [(13.5, 0.13), (12.5, 0.13), (12.5, 0.13)]


# ----------------------------------------------------------------------------- the request


class TestRequestShape:
    def test_parameters(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(41.88, -87.63, 0), q(39.74, -104.99, 2)])
        [params] = session.calls
        assert params == {
            "latitude": "39.74,41.88",  # sorted for a stable request
            "longitude": "-104.99,-87.63",
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "start_hour": "2026-11-09T12:00",
            "end_hour": "2026-11-09T14:00",
        }

    def test_the_request_never_uses_forecast_hours_or_models(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(41.88, -87.63)])
        assert "forecast_hours" not in session.calls[0]
        assert "models" not in session.calls[0]

    def test_the_window_is_anchored_at_the_needed_hours_not_at_now(self):
        session = answering()
        client, _ = make_client(session)
        departure = datetime(2027, 3, 1, 5, tzinfo=UTC)
        client.get_weather_at([WeatherQuery(41.88, -87.63, departure + timedelta(hours=7))])
        assert session.calls[0]["start_hour"] == "2027-03-01T12:00"
        assert session.calls[0]["end_hour"] == "2027-03-01T12:00"

    def test_a_single_location_works(self):
        client, _ = make_client(answering())
        [sample] = client.get_weather_at([q(41.88, -87.63)])
        assert isinstance(sample, WeatherSample)


# ----------------------------------------------------------------------------- the answers


class TestMatchingEtaToForecast:
    def test_each_query_gets_the_hour_nearest_to_its_eta(self):
        client, _ = make_client(answering())
        samples = client.get_weather_at(
            [q(40.0, -90.0, 1, 10), q(40.0, -90.0, 1, 40), q(40.0, -90.0, 2, 29), q(40.0, -90.0, 2, 30)]
        )
        # wind = lat + hour/100 -> the hour that was used shows in the fractional part
        assert [round(s.wind_mph, 2) for s in samples] == [40.13, 40.14, 40.14, 40.15]

    def test_results_follow_the_order_of_the_queries(self):
        client, _ = make_client(answering())
        queries = [q(45.0, -90.0, 3), q(30.0, -80.0, 0), q(45.0, -90.0, 3), q(35.0, -85.0, 1)]
        samples = client.get_weather_at(queries)
        assert [round(s.wind_mph, 2) for s in samples] == [45.15, 30.12, 45.15, 35.13]

    def test_eta_in_another_time_zone_uses_the_utc_hour(self):
        client, _ = make_client(answering())
        seoul = timezone(timedelta(hours=9))
        eta = datetime(2026, 11, 9, 21, 5, tzinfo=seoul)  # 12:05 UTC
        [sample] = client.get_weather_at([WeatherQuery(40.0, -90.0, eta)])
        assert round(sample.wind_mph, 2) == 40.12

    def test_values_are_in_the_risk_table_units(self):
        client, _ = make_client(answering(value=lambda *_: (31.5, 0.2, 0.05, 0.7)))
        [sample] = client.get_weather_at([q(40.0, -90.0)])
        assert sample == WeatherSample(wind_mph=31.5, rain_in_hr=0.25, snow_in_hr=0.7)

    def test_no_queries_make_no_calls(self):
        session = answering()
        client, _ = make_client(session)
        assert client.get_weather_at([]) == []
        assert session.calls == []

    def test_a_naive_eta_is_rejected(self):
        client, _ = make_client(answering())
        with pytest.raises(ValueError, match="timezone-aware"):
            client.get_weather_at([WeatherQuery(40.0, -90.0, datetime(2026, 11, 9, 12))])


class TestDeduplication:
    def test_equal_position_and_hour_are_fetched_once(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(41.881, -87.631), q(41.884, -87.634), q(41.88, -87.63, 0, 20)])
        assert session.calls[0]["latitude"] == "41.88"  # one location, not three

    def test_same_place_at_different_hours_is_one_location(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0, 0), q(40.0, -90.0, 5)])
        assert len(session.calls) == 1
        assert session.calls[0]["latitude"] == "40.00"
        assert session.calls[0]["end_hour"] == "2026-11-09T17:00"


class TestBatching:
    def test_requests_hold_at_most_200_locations(self):
        session = answering()
        client, _ = make_client(session)
        queries = [q(30.0 + i * 0.01, -90.0, i % 5) for i in range(450)]
        samples = client.get_weather_at(queries)
        sizes = sorted(len(c["latitude"].split(",")) for c in session.calls)
        assert sizes == [50, 200, 200]
        assert max(sizes) <= MAX_LOCATIONS_PER_REQUEST
        # the order of the answers is the order of the queries
        for i, sample in enumerate(samples):
            assert round(sample.wind_mph, 2) == round(30.0 + i * 0.01 + (12 + i % 5) / 100, 2)

    def test_exactly_200_locations_is_one_request(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(30.0 + i * 0.01, -90.0) for i in range(200)])
        assert len(session.calls) == 1

    def test_201_locations_is_two_requests(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(30.0 + i * 0.01, -90.0) for i in range(201)])
        assert sorted(len(c["latitude"].split(",")) for c in session.calls) == [1, 200]

    def test_each_batch_asks_only_for_its_own_hours(self):
        session = answering()
        client, _ = make_client(session)
        early = [q(30.0 + i * 0.01, -90.0, 0) for i in range(200)]  # sorted first: lowest lat
        late = [q(40.0 + i * 0.01, -90.0, 30) for i in range(10)]
        client.get_weather_at(early + late)
        windows = {(c["start_hour"], c["end_hour"]) for c in session.calls}
        assert windows == {
            ("2026-11-09T12:00", "2026-11-09T12:00"),
            ("2026-11-10T18:00", "2026-11-10T18:00"),
        }


# ----------------------------------------------------------------------------------- cache


class TestCache:
    def test_a_repeat_makes_no_calls(self):
        session = answering()
        client, _ = make_client(session)
        queries = [q(40.0, -90.0, 0), q(41.0, -91.0, 3)]
        first = client.get_weather_at(queries)
        second = client.get_weather_at(queries)
        assert len(session.calls) == 1
        assert first == second

    def test_only_missing_pairs_are_fetched(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0, 0)])
        client.get_weather_at([q(40.0, -90.0, 0), q(41.0, -91.0, 0)])
        assert [c["latitude"] for c in session.calls] == ["40.00", "41.00"]

    def test_other_hours_of_the_window_are_cached_as_well(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0, 0), q(40.0, -90.0, 4)])  # window 12:00..16:00
        client.get_weather_at([q(40.0, -90.0, 2)])  # an hour in the middle
        assert len(session.calls) == 1

    def test_places_sharing_a_latitude_or_longitude_do_not_share_an_entry(self):
        def value(lat, lon, hour):
            return (lat + abs(lon) / 1000, 0.0, 0.0, 0.0)  # the wind tells lat and lon apart

        session = answering(value=value)
        client, _ = make_client(session)
        [a] = client.get_weather_at([q(40.0, -90.0)])
        [same_lat] = client.get_weather_at([q(40.0, -91.0)])
        [same_lon] = client.get_weather_at([q(41.0, -90.0)])
        assert len(session.calls) == 3
        assert (a.wind_mph, same_lat.wind_mph, same_lon.wind_mph) == pytest.approx(
            (40.09, 40.091, 41.09)
        )

    def test_a_different_hour_of_the_same_place_is_fetched(self):
        session = answering()
        client, _ = make_client(session)
        client.get_weather_at([q(40.0, -90.0, 0)])
        client.get_weather_at([q(40.0, -90.0, 10)])
        assert len(session.calls) == 2

    def test_cache_entries_expire_after_an_hour(self):
        cache = DictCache()
        client, _ = make_client(answering(), cache)
        client.get_weather_at([q(40.0, -90.0)])
        assert cache.timeout == 3600

    def test_a_failed_request_caches_nothing(self):
        session = FakeSession(lambda p: FakeResponse(500, {}))
        cache = DictCache()
        client, _ = make_client(session, cache)
        with pytest.raises(WeatherUnavailable):
            client.get_weather_at([q(40.0, -90.0)])
        assert cache.data == {}

    def test_null_hours_are_never_cached_but_good_hours_are(self):
        cache = DictCache()
        # Hours from 14:00 on are null. Ask for 12:00 (good) and 15:00 (null).
        session = answering(null_from=datetime(2026, 11, 9, 14))
        client, _ = make_client(session, cache)
        with pytest.raises(ForecastOutOfRange):
            client.get_weather_at([q(40.0, -90.0, 0), q(40.0, -90.0, 3)])

        cached_hours = sorted(key.rsplit(":", 1)[1] for key in cache.data)
        assert cached_hours == ["20261109T12", "20261109T13"]  # 14, 15 were null: not stored

        # the good hour is now served from the cache without another call
        calls_before = len(session.calls)
        [sample] = client.get_weather_at([q(40.0, -90.0, 0)])
        assert len(session.calls) == calls_before
        assert sample.wind_mph == pytest.approx(40.12)

    def test_works_with_the_real_django_cache(self):
        from django.core.cache import caches

        caches["default"].clear()
        session = answering()
        client = WeatherClient(session=session, sleep=lambda s: None)  # default cache
        queries = [q(40.0, -90.0, 0), q(41.0, -91.0, 3)]
        first = client.get_weather_at(queries)
        second = client.get_weather_at(queries)
        assert len(session.calls) == 1
        assert first == second
        caches["default"].clear()


# ----------------------------------------------------------------------- retries and errors


class TestRetries:
    def test_rate_limit_then_success(self):
        answers = [FakeResponse(429, {"error": True}), None]

        def handler(params):
            answer = answers.pop(0)
            return answer or FakeResponse(200, body_for(params))

        session = FakeSession(handler)
        client, sleeps = make_client(session)
        client.get_weather_at([q(40.0, -90.0)])
        assert len(session.calls) == 2
        assert sleeps == [1.0]

    def test_gives_up_after_three_attempts_with_growing_pauses(self):
        session = FakeSession(lambda p: FakeResponse(429, {"error": True}))
        client, sleeps = make_client(session)
        with pytest.raises(WeatherUnavailable, match=r"Open-Meteo is not responding \(HTTP 429\)"):
            client.get_weather_at([q(40.0, -90.0)])
        assert len(session.calls) == 3
        assert sleeps == [1.0, 2.0]

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_server_errors_are_retried(self, status):
        session = FakeSession(lambda p: FakeResponse(status, {}))
        client, _ = make_client(session)
        with pytest.raises(WeatherUnavailable):
            client.get_weather_at([q(40.0, -90.0)])
        assert len(session.calls) == 3

    @pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError()])
    def test_network_failures_are_retried_then_reported(self, error):
        session = FakeSession(lambda p: error)
        client, _ = make_client(session)
        with pytest.raises(WeatherUnavailable, match=type(error).__name__):
            client.get_weather_at([q(40.0, -90.0)])
        assert len(session.calls) == 3

    def test_a_network_failure_then_success(self):
        answers = [requests.Timeout(), None]

        def handler(params):
            answer = answers.pop(0)
            return answer or FakeResponse(200, body_for(params))

        client, _ = make_client(FakeSession(handler))
        [sample] = client.get_weather_at([q(40.0, -90.0)])
        assert sample.wind_mph == pytest.approx(40.12)

    @pytest.mark.parametrize("status", [401, 403, 404, 418])
    def test_other_client_errors_are_not_retried(self, status):
        session = FakeSession(lambda p: FakeResponse(status, {}))
        client, sleeps = make_client(session)
        with pytest.raises(WeatherUnavailable, match=str(status)):
            client.get_weather_at([q(40.0, -90.0)])
        assert len(session.calls) == 1 and sleeps == []

    def test_a_body_that_is_not_json(self):
        session = FakeSession(lambda p: FakeResponse(200, not_json=True))
        client, _ = make_client(session)
        with pytest.raises(WeatherUnavailable, match="not JSON"):
            client.get_weather_at([q(40.0, -90.0)])

    def test_a_bad_request_that_is_not_a_range_error(self):
        reason = "Latitude must be in range of -90 to 90°. Given: 95.0."
        session = FakeSession(lambda p: FakeResponse(400, {"error": True, "reason": reason}))
        client, _ = make_client(session)
        with pytest.raises(WeatherUnavailable, match="Latitude must be"):
            client.get_weather_at([q(40.0, -90.0)])
        assert len(session.calls) == 1

    def test_a_400_without_a_json_object(self):
        session = FakeSession(lambda p: FakeResponse(400, "nope"))
        client, _ = make_client(session)
        with pytest.raises(WeatherUnavailable):
            client.get_weather_at([q(40.0, -90.0)])

    def test_one_failing_batch_fails_the_whole_call(self):
        def handler(params):
            if params["latitude"].startswith("30."):
                return FakeResponse(500, {})
            return FakeResponse(200, body_for(params))

        client, _ = make_client(FakeSession(handler))
        queries = [q(30.0 + i * 0.01, -90.0) for i in range(200)] + [q(50.0, -90.0)]
        with pytest.raises(WeatherUnavailable):
            client.get_weather_at(queries)


# ---------------------------------------------------------------------- forecast out of range


class TestForecastOutOfRange:
    LAST_DAY = "2026-11-21"
    RANGE_REASON = "Parameter 'end_hour' is out of allowed range from 2026-08-05 to 2026-11-21"

    def range_error_session(self, probe_good_until=18, probe_status=200):
        """HTTP 400 for the real request; the one-day probe answers with data until 18:00."""

        def handler(params):
            if params["start_hour"].startswith(self.LAST_DAY) and params["end_hour"].endswith("23:00"):
                if probe_status != 200:
                    return FakeResponse(probe_status, {})
                null_from = datetime(2026, 11, 21, probe_good_until + 1)
                return FakeResponse(200, body_for(params, null_from=null_from))
            return FakeResponse(400, {"error": True, "reason": self.RANGE_REASON})

        return FakeSession(handler)

    def far(self):
        return WeatherQuery(40.0, -90.0, datetime(2026, 12, 30, 12, tzinfo=UTC))

    def test_http_400_is_out_of_range_and_reports_the_last_forecast_hour(self):
        client, _ = make_client(self.range_error_session())
        with pytest.raises(ForecastOutOfRange) as caught:
            client.get_weather_at([self.far()])
        assert caught.value.forecast_end == datetime(2026, 11, 21, 18, tzinfo=UTC)

    def test_the_probe_is_one_extra_call_for_one_location(self):
        session = self.range_error_session()
        client, _ = make_client(session)
        with pytest.raises(ForecastOutOfRange):
            client.get_weather_at([self.far(), WeatherQuery(41.0, -91.0, self.far().time)])
        assert len(session.calls) == 2
        assert session.calls[1]["latitude"] == "40.00"
        assert session.calls[1]["start_hour"] == "2026-11-21T00:00"
        assert session.calls[1]["end_hour"] == "2026-11-21T23:00"

    @pytest.mark.parametrize("probe_status", [500, 404, 400])
    def test_a_failing_probe_still_reports_out_of_range(self, probe_status):
        client, _ = make_client(self.range_error_session(probe_status=probe_status))
        with pytest.raises(ForecastOutOfRange) as caught:
            client.get_weather_at([self.far()])
        assert caught.value.forecast_end is None

    def test_nulls_at_the_end_of_the_forecast(self):
        null_from = datetime(2026, 11, 21, 19)
        client, _ = make_client(answering(null_from=null_from))
        eta = WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 18, tzinfo=UTC))
        late = WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 21, tzinfo=UTC))
        with pytest.raises(ForecastOutOfRange) as caught:
            client.get_weather_at([eta, late])
        assert caught.value.forecast_end == datetime(2026, 11, 21, 18, tzinfo=UTC)

    def test_a_window_that_is_all_null_still_reports_the_forecast_end(self):
        # Only 21:00 is asked for and it is null, so the answer has no good hour to read the end
        # from. A one-day probe finds it.
        session = answering(null_from=datetime(2026, 11, 21, 19))
        client, _ = make_client(session)
        late = WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 21, tzinfo=UTC))
        with pytest.raises(ForecastOutOfRange) as caught:
            client.get_weather_at([late])
        assert caught.value.forecast_end == datetime(2026, 11, 21, 18, tzinfo=UTC)
        assert session.calls[1]["start_hour"] == "2026-11-21T00:00"

    def test_a_window_that_is_all_null_with_a_failing_probe(self):
        def handler(params):
            if params["start_hour"] == params["end_hour"]:
                return FakeResponse(200, body_for(params, null_from=datetime(2026, 11, 21, 0)))
            return FakeResponse(500, {})

        client, _ = make_client(FakeSession(handler))
        late = WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 21, tzinfo=UTC))
        with pytest.raises(ForecastOutOfRange) as caught:
            client.get_weather_at([late])
        assert caught.value.forecast_end is None

    def test_the_last_good_hour_is_still_usable(self):
        client, _ = make_client(answering(null_from=datetime(2026, 11, 21, 19)))
        [sample] = client.get_weather_at(
            [WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 18, 0, tzinfo=UTC))]
        )
        assert sample.wind_mph == pytest.approx(40.18)

    def test_a_time_inside_the_first_missing_hour_is_out_of_range(self):
        # 18:20 needs the wind of 18:00 (there) and the rain of 18:00 to 19:00 (missing).
        client, _ = make_client(answering(null_from=datetime(2026, 11, 21, 19)))
        with pytest.raises(ForecastOutOfRange) as caught:
            client.get_weather_at([WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 18, 20, tzinfo=UTC))])
        assert caught.value.forecast_end == datetime(2026, 11, 21, 18, tzinfo=UTC)

    def test_a_null_is_never_returned_as_zero(self):
        client, _ = make_client(answering(null_from=datetime(2026, 11, 21, 19)))
        queries = [WeatherQuery(40.0, -90.0, datetime(2026, 11, 21, 19, tzinfo=UTC))]
        with pytest.raises(ForecastOutOfRange):
            client.get_weather_at(queries)

    def test_one_null_location_among_good_ones_still_fails(self):
        # Location 41.0 has no data for the hour; the others do. The call must fail, not skip it.
        def value(lat, lon, hour):
            return (None, None, None, None) if lat == 41.0 else (5.0, 0.0, 0.0, 0.0)

        client, _ = make_client(answering(value=value))
        with pytest.raises(ForecastOutOfRange):
            client.get_weather_at([q(40.0, -90.0), q(41.0, -91.0), q(42.0, -92.0)])

    def test_a_null_in_the_middle_of_a_window_is_unavailable(self):
        def value(lat, lon, hour):
            return (None,) * 4 if hour.hour == 13 else (5.0, 0.0, 0.0, 0.0)

        client, _ = make_client(answering(value=value))
        with pytest.raises(WeatherUnavailable):
            client.get_weather_at([q(40.0, -90.0, 0), q(40.0, -90.0, 1), q(40.0, -90.0, 2)])


class TestGuardsAgainstBadAnswers:
    def test_wrong_number_of_locations_returned(self):
        def handler(params):
            body = body_for(params)
            return FakeResponse(200, body[:1])

        client, _ = make_client(FakeSession(handler))
        with pytest.raises(WeatherUnavailable, match="expected 2"):
            client.get_weather_at([q(40.0, -90.0), q(41.0, -91.0)])

    def test_more_locations_returned_than_requested(self):
        def handler(params):
            body = body_for(dict(params, latitude="40.00,41.00,42.00", longitude="-90.00,-91.00,-92.00"))
            return FakeResponse(200, body)

        client, _ = make_client(FakeSession(handler))
        with pytest.raises(WeatherUnavailable, match="expected 2"):
            client.get_weather_at([q(40.0, -90.0), q(41.0, -91.0)])

    def test_wrong_units_are_refused(self):
        def handler(params):
            body = body_for(params)
            body["hourly_units"] = dict(UNITS, wind_speed_10m="km/h")
            return FakeResponse(200, body)

        client, _ = make_client(FakeSession(handler))
        with pytest.raises(WeatherUnavailable, match="units"):
            client.get_weather_at([q(40.0, -90.0)])

    def test_nothing_is_cached_from_a_rejected_answer(self):
        def handler(params):
            body = body_for(params)
            body["hourly_units"] = dict(UNITS, snowfall="cm")
            return FakeResponse(200, body)

        cache = DictCache()
        client, _ = make_client(FakeSession(handler), cache)
        with pytest.raises(WeatherUnavailable):
            client.get_weather_at([q(40.0, -90.0)])
        assert cache.data == {}


def test_get_client_returns_one_shared_instance(monkeypatch):
    monkeypatch.setattr(weather_client, "_default_client", None)
    assert weather_client.get_client() is weather_client.get_client()
