"""Tests for trip/weather.py: hour matching, response parsing, and the never-fill-with-0 rule."""

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from trip.risk import RiskLevel, classify_rain, classify_snow, classify_wind
from trip.weather import (
    ForecastOutOfRange,
    HourlySeries,
    WeatherSample,
    WeatherUnavailable,
    nearest_hour,
    parse_range_error,
    parse_response,
    round_location,
)

UTC = timezone.utc
H12 = datetime(2026, 11, 9, 12, tzinfo=UTC)

UNITS = {
    "time": "iso8601",
    "wind_speed_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}


def entry(times, wind, rain, showers, snow, units=None):
    """One location's Open-Meteo answer."""
    return {
        "latitude": 41.88,
        "longitude": -87.65,
        "hourly_units": UNITS if units is None else units,
        "hourly": {
            "time": times,
            "wind_speed_10m": wind,
            "rain": rain,
            "showers": showers,
            "snowfall": snow,
        },
    }


def simple_entry(**override):
    columns = dict(
        times=["2026-11-09T12:00", "2026-11-09T13:00"],
        wind=[10.0, 20.0],
        rain=[0.0, 0.2],
        showers=[0.0, 0.05],
        snow=[0.0, 0.6],
    )
    columns.update(override)
    return entry(**columns)


# --------------------------------------------------------------------------- nearest_hour


class TestNearestHour:
    def test_exact_hour_is_unchanged(self):
        assert nearest_hour(H12) == H12

    def test_before_half_past_rounds_down(self):
        assert nearest_hour(H12 + timedelta(minutes=29, seconds=59)) == H12

    def test_half_past_rounds_up(self):
        assert nearest_hour(H12 + timedelta(minutes=30)) == H12 + timedelta(hours=1)

    def test_just_under_the_next_hour_rounds_up(self):
        assert nearest_hour(H12 + timedelta(minutes=59, seconds=59)) == H12 + timedelta(hours=1)

    def test_microseconds_are_considered(self):
        just_before_half = H12 + timedelta(minutes=29, seconds=59, microseconds=999_999)
        assert nearest_hour(just_before_half) == H12

    def test_rounding_up_crosses_midnight(self):
        moment = datetime(2026, 11, 9, 23, 45, tzinfo=UTC)
        assert nearest_hour(moment) == datetime(2026, 11, 10, 0, tzinfo=UTC)

    def test_result_is_utc_whatever_the_input_offset(self):
        seoul = timezone(timedelta(hours=9))
        moment = datetime(2026, 11, 9, 21, 10, tzinfo=seoul)  # 12:10 UTC
        result = nearest_hour(moment)
        assert result == H12
        assert result.utcoffset() == timedelta(0)

    def test_half_hour_offset_zone_is_converted_before_rounding(self):
        india = timezone(timedelta(hours=5, minutes=30))
        moment = datetime(2026, 11, 9, 17, 40, tzinfo=india)  # 12:10 UTC
        assert nearest_hour(moment) == H12

    def test_across_the_us_fall_back_date(self):
        # 2026-11-01: 06:50 UTC is 01:50 CST (second 01:xx), 05:50 UTC is 01:50 CDT.
        chicago_fall = timezone(timedelta(hours=-6))
        moment = datetime(2026, 11, 1, 1, 50, tzinfo=chicago_fall)  # 07:50 UTC
        assert nearest_hour(moment) == datetime(2026, 11, 1, 8, tzinfo=UTC)

    def test_naive_time_is_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            nearest_hour(datetime(2026, 11, 9, 12))


# -------------------------------------------------------------------------- round_location


class TestRoundLocation:
    def test_rounds_to_two_decimals(self):
        assert round_location(41.8795, -87.6497) == (41.88, -87.65)

    def test_nearby_points_share_a_key(self):
        assert round_location(41.8801, -87.6301) == round_location(41.8849, -87.6349)

    def test_negative_zero_is_normalised(self):
        lat, lon = round_location(-0.001, -0.002)
        assert str(lat) == "0.0" and str(lon) == "0.0"

    @pytest.mark.parametrize("bad", [(91, 0), (-91, 0), (0, 181), (0, -181)])
    def test_out_of_range_is_rejected(self, bad):
        with pytest.raises(ValueError):
            round_location(*bad)

    @pytest.mark.parametrize("bad", [(math.nan, 0), (0, math.inf), (-math.inf, 0)])
    def test_not_finite_is_rejected(self, bad):
        with pytest.raises(ValueError):
            round_location(*bad)

    def test_the_poles_and_antimeridian_are_valid(self):
        assert round_location(90, 180) == (90.0, 180.0)
        assert round_location(-90, -180) == (-90.0, -180.0)


# -------------------------------------------------------------------------- parse_response


class TestParseResponse:
    def test_single_location_object(self):
        [series] = parse_response(simple_entry(), 1)
        assert series.sample_at(H12) == WeatherSample(10.0, 0.0, 0.0)

    def test_several_locations_keep_request_order(self):
        first = simple_entry(wind=[1.0, 2.0])
        second = simple_entry(wind=[3.0, 4.0])
        a, b = parse_response([first, second], 2)
        assert a.sample_at(H12).wind_mph == 1.0
        assert b.sample_at(H12).wind_mph == 3.0

    def test_rain_is_rain_plus_showers_and_snow_is_snowfall(self):
        [series] = parse_response(simple_entry(), 1)
        assert series.sample_at(H12 + timedelta(hours=1)) == WeatherSample(
            wind_mph=20.0, rain_in_hr=0.25, snow_in_hr=0.6
        )

    def test_times_are_utc_aware(self):
        [series] = parse_response(simple_entry(), 1)
        assert all(hour.utcoffset() == timedelta(0) for hour in series.samples)

    def test_integer_values_are_accepted(self):
        [series] = parse_response(simple_entry(wind=[10, 20], rain=[0, 0], showers=[0, 0], snow=[0, 0]), 1)
        assert series.sample_at(H12).wind_mph == 10.0

    def test_mph_label_is_accepted_too(self):
        units = dict(UNITS, wind_speed_10m="mph")
        [series] = parse_response(simple_entry(units=units), 1)
        assert series.sample_at(H12).wind_mph == 10.0

    def test_float_noise_in_the_rain_sum_does_not_cross_a_boundary(self):
        # 0.09 + 0.01 is 0.09999999999999999 in floating point: it would be Low, but the rain
        # really is 0.10 in/hr, which the table makes Moderate.
        assert 0.09 + 0.01 < 0.10
        [series] = parse_response(simple_entry(rain=[0.09, 0.0], showers=[0.01, 0.0]), 1)
        rain = series.sample_at(H12).rain_in_hr
        assert rain == 0.10
        assert classify_rain(rain) == RiskLevel.MODERATE

    def test_boundary_values_classify_as_the_table_says(self):
        [series] = parse_response(
            simple_entry(wind=[35.0, 55.0], rain=[0.25, 1.0], showers=[0.0, 0.0], snow=[1.0, 3.0]), 1
        )
        first = series.sample_at(H12)
        second = series.sample_at(H12 + timedelta(hours=1))
        assert classify_wind(first.wind_mph) == RiskLevel.HIGH
        assert classify_rain(first.rain_in_hr) == RiskLevel.HIGH
        assert classify_snow(first.snow_in_hr) == RiskLevel.HIGH
        assert classify_wind(second.wind_mph) == RiskLevel.NO_TRAVEL
        assert classify_rain(second.rain_in_hr) == RiskLevel.SEVERE
        assert classify_snow(second.snow_in_hr) == RiskLevel.SEVERE

    # -- shape and consistency

    def test_location_count_mismatch(self):
        with pytest.raises(WeatherUnavailable, match="expected 2"):
            parse_response([simple_entry()], 2)

    def test_single_object_when_several_were_requested(self):
        with pytest.raises(WeatherUnavailable):
            parse_response(simple_entry(), 3)

    def test_error_body(self):
        with pytest.raises(WeatherUnavailable, match="bad thing"):
            parse_response({"error": True, "reason": "bad thing"}, 1)

    @pytest.mark.parametrize("payload", [None, "oops", 7, [None], [{}], [{"hourly": "x"}]])
    def test_not_the_expected_format(self, payload):
        with pytest.raises(WeatherUnavailable):
            parse_response(payload, 1)

    def test_columns_of_different_length(self):
        with pytest.raises(WeatherUnavailable, match="different lengths"):
            parse_response(simple_entry(wind=[1.0]), 1)

    def test_missing_variable(self):
        broken = simple_entry()
        del broken["hourly"]["snowfall"]
        with pytest.raises(WeatherUnavailable, match="missing a variable"):
            parse_response(broken, 1)

    @pytest.mark.parametrize(
        "units",
        [
            dict(UNITS, wind_speed_10m="km/h"),
            dict(UNITS, wind_speed_10m="m/s"),
            dict(UNITS, rain="mm"),
            dict(UNITS, showers="mm"),
            dict(UNITS, snowfall="cm"),
            {k: v for k, v in UNITS.items() if k != "rain"},
        ],
    )
    def test_unexpected_units_are_refused(self, units):
        with pytest.raises(WeatherUnavailable, match="units"):
            parse_response(simple_entry(units=units), 1)

    def test_units_missing_entirely(self):
        broken = simple_entry()
        del broken["hourly_units"]
        with pytest.raises(WeatherUnavailable, match="units"):
            parse_response(broken, 1)

    @pytest.mark.parametrize(
        "bad",
        ["5", True, [1], -1.0, math.nan, math.inf],
        ids=["string", "bool", "list", "negative", "nan", "inf"],
    )
    @pytest.mark.parametrize("column", ["wind", "rain", "showers", "snow"])
    def test_garbage_values_are_errors_not_zero(self, column, bad):
        with pytest.raises(WeatherUnavailable):
            parse_response(simple_entry(**{column: [bad, 0.0]}), 1)

    def test_invalid_time_label(self):
        with pytest.raises(WeatherUnavailable, match="invalid time"):
            parse_response(simple_entry(times=["yesterday", "2026-11-09T13:00"]), 1)

    # -- null handling

    @pytest.mark.parametrize("column", ["wind", "rain", "showers", "snow"])
    def test_a_null_in_any_variable_makes_the_hour_null_not_zero(self, column):
        [series] = parse_response(simple_entry(**{column: [None, 0.0]}), 1)
        assert H12 not in series.samples
        assert H12 in series.null_hours
        assert H12 + timedelta(hours=1) in series.samples


# ----------------------------------------------------------------------------- sample_at


class TestSampleAt:
    TIMES = [f"2026-11-21T{h:02d}:00" for h in range(16, 22)]  # 16..21

    def series(self, last_good_hour=18):
        n = len(self.TIMES)
        wind = [5.0 if int(t[11:13]) <= last_good_hour else None for t in self.TIMES]
        zeros = [0.0 if w is not None else None for w in wind]
        return parse_response(entry(self.TIMES, wind, zeros, zeros, zeros), 1)[0]

    def hour(self, h):
        return datetime(2026, 11, 21, h, tzinfo=UTC)

    def test_a_good_hour(self):
        assert self.series().sample_at(self.hour(18)).wind_mph == 5.0

    def test_null_after_the_last_good_hour_is_the_forecast_end(self):
        with pytest.raises(ForecastOutOfRange) as caught:
            self.series().sample_at(self.hour(19))
        assert caught.value.forecast_end == self.hour(18)

    def test_the_last_null_hour_too(self):
        with pytest.raises(ForecastOutOfRange):
            self.series().sample_at(self.hour(21))

    def test_all_null_is_out_of_range_with_unknown_end(self):
        n = len(self.TIMES)
        nulls = [None] * n
        series = parse_response(entry(self.TIMES, nulls, nulls, nulls, nulls), 1)[0]
        with pytest.raises(ForecastOutOfRange) as caught:
            series.sample_at(self.hour(17))
        assert caught.value.forecast_end is None

    def test_null_in_the_middle_is_broken_data_not_the_end(self):
        wind = [5.0, None, 5.0]
        zeros = [0.0, None, 0.0]
        series = parse_response(
            entry(["2026-11-21T16:00", "2026-11-21T17:00", "2026-11-21T18:00"], wind, zeros, zeros, zeros), 1
        )[0]
        with pytest.raises(WeatherUnavailable):
            series.sample_at(self.hour(17))

    def test_an_hour_the_answer_does_not_contain(self):
        with pytest.raises(WeatherUnavailable):
            self.series().sample_at(self.hour(23))
        with pytest.raises(WeatherUnavailable):
            self.series().sample_at(self.hour(10))

    def test_empty_series(self):
        empty = HourlySeries(samples={}, null_hours=frozenset())
        with pytest.raises(WeatherUnavailable):
            empty.sample_at(H12)


# ------------------------------------------------------------------------ parse_range_error


class TestParseRangeError:
    def test_real_message_for_start_hour(self):
        reason = "Parameter 'start_hour' is out of allowed range from 2026-08-05 to 2026-11-21"
        assert parse_range_error(reason) == date(2026, 11, 21)

    def test_real_message_for_end_hour(self):
        reason = "Parameter 'end_hour' is out of allowed range from 2026-08-05 to 2026-11-21"
        assert parse_range_error(reason) == date(2026, 11, 21)

    @pytest.mark.parametrize(
        "reason",
        [
            "Latitude must be in range of -90 to 90°. Given: 95.0.",
            "Invalid value: Cannot initialize Float from invalid String value abc",
            "",
            None,
            "out of allowed range from 2026-08-05",
        ],
    )
    def test_other_errors_are_not_range_errors(self, reason):
        assert parse_range_error(reason) is None
