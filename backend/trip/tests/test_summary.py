"""Tests for trip/summary.py: miles per level, average risk, rounding, validation."""

import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from trip.risk import RiskLevel
from trip.summary import RouteSummary, Stretch, round_half_up, summarize_route

UTC = timezone.utc
DEPART = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
L, M, H, S, N = (RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)


def summary(stretches, seconds=3600, departure=DEPART):
    return summarize_route([Stretch(level, miles) for level, miles in stretches], seconds, departure)


# ------------------------------------------------------------------------- round_half_up


class TestRoundHalfUp:
    @pytest.mark.parametrize(
        "value, expected",
        [(0.4, 0), (0.5, 1), (1.5, 2), (2.5, 3), (24.5, 25), (24.49, 24), (24.51, 25), (0, 0), (100.0, 100)],
    )
    def test_whole_numbers_halves_go_up(self, value, expected):
        result = round_half_up(value)
        assert result == expected and isinstance(result, int)

    @pytest.mark.parametrize(
        "value, expected",
        [(0.325, 0.33), (0.335, 0.34), (0.285, 0.29), (0.005, 0.01), (0.004, 0.0), (1.005, 1.01), (2.675, 2.68)],
    )
    def test_two_decimals_halves_go_up(self, value, expected):
        # Python's round() gives 0.32, 0.34, 0.28, 0.01, 1.0, 2.67 for several of these
        assert round_half_up(value, 2) == expected

    def test_differs_from_pythons_round_on_exact_halves(self):
        assert round(24.5) == 24 and round_half_up(24.5) == 25
        assert round(2.5) == 2 and round_half_up(2.5) == 3

    def test_noise_just_below_a_half_is_cleaned(self):
        assert round_half_up(24.499999999999996) == 25
        assert round_half_up(24.4999) == 24  # a real difference is kept


# --------------------------------------------------------------------------- miles by level


class TestMilesByLevel:
    def test_miles_are_added_per_level(self):
        s = summary([(L, 10.0), (S, 5.0), (L, 7.0), (H, 3.0), (S, 2.0)])
        assert s.miles_by_level == {L: 17, M: 0, H: 3, S: 7, N: 0}

    def test_severe_and_high_miles_are_their_own_levels_only(self):
        s = summary([(S, 10.0), (H, 20.0), (N, 5.0), (M, 1.0)])
        assert s.severe_miles == 10  # No Travel miles are not Severe miles
        assert s.high_miles == 20  # Severe miles are not High miles

    def test_a_route_with_no_risk(self):
        s = summary([(L, 40.0), (L, 60.0)])
        assert (s.severe_miles, s.high_miles, s.avg_risk, s.has_no_travel) == (0, 0, 0.0, False)
        assert s.distance_miles == 100

    def test_every_level_is_present_even_at_zero(self):
        assert set(summary([(L, 5.0)]).miles_by_level) == set(RiskLevel)

    def test_levels_are_summed_not_counted(self):
        # one long Severe stretch beats several short ones: miles, not checkpoint count
        long_stretch = summary([(S, 50.0), (L, 50.0)])
        many_short = summary([(S, 5.0), (L, 20.0), (S, 5.0), (L, 20.0), (S, 5.0), (L, 45.0)])
        assert long_stretch.severe_miles == 50 and many_short.severe_miles == 15

    def test_distance_is_the_sum_of_the_stretches(self):
        assert summary([(L, 12.5), (M, 25.0), (H, 12.5)]).distance_miles == 50

    def test_distance_rounds_half_up(self):
        assert summary([(L, 10.25), (M, 10.25)]).distance_miles == 21  # 20.5

    def test_each_level_rounds_half_up(self):
        s = summary([(S, 24.5), (H, 0.5), (M, 2.5)])
        assert (s.severe_miles, s.high_miles, s.miles_by_level[M]) == (25, 1, 3)

    def test_level_miles_add_up_to_distance_within_rounding(self):
        rng = random.Random(7)
        for _ in range(200):
            stretches = [(rng.choice(list(RiskLevel)), rng.uniform(0.1, 40)) for _ in range(rng.randint(1, 30))]
            s = summary(stretches)
            assert abs(sum(s.miles_by_level.values()) - s.distance_miles) <= 2.5


# ----------------------------------------------------------------------------- average risk


class TestAverageRisk:
    def test_weighted_by_length(self):
        # (0*30 + 1*10 + 2*10 + 3*10 + 4*40) / 100 = 2.2
        s = summary([(L, 30.0), (M, 10.0), (H, 10.0), (S, 10.0), (N, 40.0)])
        assert s.avg_risk == 2.2

    def test_length_matters_not_the_number_of_checkpoints(self):
        s = summary([(S, 90.0), (L, 5.0), (L, 5.0)])  # 3 checkpoints, 90% of the miles Severe
        assert s.avg_risk == 2.7

    def test_the_contract_example(self):
        # docs/api-contract.md: low 790, moderate 130, high 61, severe 25 -> avg_risk 0.33
        s = summary([(L, 790.0), (M, 130.0), (H, 61.0), (S, 25.0)])
        assert s.avg_risk == 0.33
        assert (s.severe_miles, s.high_miles, s.distance_miles) == (25, 61, 1006)

    def test_two_decimals_half_up(self):
        # 0.325 exactly: (1*32.5) / 100
        assert summary([(M, 32.5), (L, 67.5)]).avg_risk == 0.33

    def test_whole_route_at_each_level(self):
        for level in RiskLevel:
            assert summary([(level, 123.0)]).avg_risk == float(int(level))

    def test_always_between_zero_and_four(self):
        rng = random.Random(3)
        for _ in range(200):
            stretches = [(rng.choice(list(RiskLevel)), rng.uniform(0.01, 30)) for _ in range(rng.randint(1, 20))]
            assert 0.0 <= summary(stretches).avg_risk <= 4.0

    def test_zero_mile_stretches_do_not_change_it(self):
        assert summary([(S, 0.0), (M, 10.0)]).avg_risk == 1.0


# -------------------------------------------------------------------------------- no travel


class TestNoTravel:
    def test_any_no_travel_stretch_flags_the_route(self):
        assert summary([(L, 90.0), (N, 0.5), (L, 9.5)]).has_no_travel is True

    def test_severe_alone_does_not(self):
        assert summary([(S, 100.0)]).has_no_travel is False


# ------------------------------------------------------------------------ time and arrival


class TestTime:
    @pytest.mark.parametrize(
        "seconds, minutes",
        [(0, 0), (29, 0), (30, 1), (89, 1), (90, 2), (3600, 60), (50_822, 847), (50_849, 847), (50_850, 848)],
    )
    def test_minutes_round_half_up(self, seconds, minutes):
        assert summary([(L, 10.0)], seconds=seconds).duration_minutes == minutes

    def test_arrival_is_departure_plus_duration(self):
        s = summary([(L, 10.0)], seconds=50_822)
        assert s.arrival == DEPART + timedelta(seconds=50_822)

    def test_arrival_is_utc_for_any_departure_offset(self):
        seoul = timezone(timedelta(hours=9))
        s = summary([(L, 10.0)], seconds=3600, departure=datetime(2026, 11, 9, 23, 0, tzinfo=seoul))
        assert s.arrival == datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
        assert s.arrival.utcoffset() == timedelta(0)

    def test_arrival_crosses_midnight(self):
        s = summary([(L, 10.0)], seconds=3 * 3600, departure=datetime(2026, 11, 9, 22, 0, tzinfo=UTC))
        assert s.arrival == datetime(2026, 11, 10, 1, 0, tzinfo=UTC)

    def test_arrival_matches_the_last_checkpoint_eta_rounding(self):
        # sampling.py rounds ETA seconds with round(); the summary must agree
        for seconds in (100.4, 100.5, 101.5, 102.5):
            s = summary([(L, 10.0)], seconds=seconds)
            assert s.arrival == DEPART + timedelta(seconds=round(seconds))


# ----------------------------------------------------------------------------- validation


class TestValidation:
    def test_no_stretches(self):
        with pytest.raises(ValueError, match="at least one"):
            summarize_route([], 100, DEPART)

    def test_zero_total_distance(self):
        with pytest.raises(ValueError, match="above zero"):
            summary([(L, 0.0)])

    @pytest.mark.parametrize("miles", [-1.0, math.nan, math.inf, -math.inf])
    def test_bad_miles(self, miles):
        with pytest.raises(ValueError, match="miles"):
            summary([(L, 10.0), (M, miles)])

    @pytest.mark.parametrize("level", [2, "high", None, 3.0])
    def test_level_must_be_a_risk_level(self, level):
        with pytest.raises(ValueError, match="RiskLevel"):
            summarize_route([Stretch(level, 10.0)], 100, DEPART)

    @pytest.mark.parametrize("seconds", [-1.0, math.nan, math.inf])
    def test_bad_duration(self, seconds):
        with pytest.raises(ValueError, match="duration"):
            summary([(L, 10.0)], seconds=seconds)

    def test_naive_departure(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            summary([(L, 10.0)], departure=datetime(2026, 11, 9, 14, 0))

    def test_result_type(self):
        assert isinstance(summary([(L, 10.0)]), RouteSummary)
