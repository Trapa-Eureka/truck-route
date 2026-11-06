"""Tests for trip/recommend.py: strict priority order, rounded ties, No Travel handling."""

import itertools
import random
from datetime import datetime, timezone

import pytest

from trip.recommend import Criterion, Recommendation, recommend
from trip.risk import RiskLevel
from trip.summary import RouteSummary, Stretch, summarize_route

UTC = timezone.utc
DEPART = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
L, M, H, S, N = (RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)


def route(severe=0, high=0, avg=0.0, minutes=600, no_travel=False):
    """A summary with exactly these display values."""
    return RouteSummary(
        distance_miles=1000,
        duration_minutes=minutes,
        arrival=DEPART,
        miles_by_level={level: 0 for level in RiskLevel},
        severe_miles=severe,
        high_miles=high,
        avg_risk=avg,
        has_no_travel=no_travel,
    )


def built(stretches, minutes=600, seconds=None):
    """A real summary computed from stretches (to test rounding end to end)."""
    duration = seconds if seconds is not None else minutes * 60
    return summarize_route([Stretch(level, miles) for level, miles in stretches], duration, DEPART)


# --------------------------------------------------------------- each criterion decides on its own


class TestEachCriterionDecides:
    def test_criterion_1_fewest_severe_miles(self):
        result = recommend({
            "A": route(severe=30, high=0, avg=0.1, minutes=500),
            "B": route(severe=10, high=99, avg=2.0, minutes=900),
            "C": route(severe=20, high=0, avg=0.1, minutes=500),
        })
        assert result.route_id == "B"
        assert result.decided_by == Criterion.SEVERE_MILES
        assert result.versus_route_id == "C"
        assert result.ranking == ("B", "C", "A")

    def test_criterion_2_fewest_high_miles_when_severe_is_tied(self):
        result = recommend({
            "A": route(severe=10, high=50, avg=0.1, minutes=500),
            "B": route(severe=10, high=20, avg=3.0, minutes=900),
        })
        assert (result.route_id, result.decided_by) == ("B", Criterion.HIGH_MILES)

    def test_criterion_3_lowest_average_risk_when_severe_and_high_are_tied(self):
        result = recommend({
            "A": route(severe=10, high=20, avg=0.80, minutes=500),
            "B": route(severe=10, high=20, avg=0.40, minutes=900),
        })
        assert (result.route_id, result.decided_by) == ("B", Criterion.AVG_RISK)

    def test_criterion_4_shortest_time_when_the_first_three_are_tied(self):
        result = recommend({
            "A": route(severe=10, high=20, avg=0.40, minutes=700),
            "B": route(severe=10, high=20, avg=0.40, minutes=650),
        })
        assert (result.route_id, result.decided_by) == ("B", Criterion.DURATION)
        assert result.versus_route_id == "A"
        assert result.duration_delta_minutes == -50  # B is 50 min faster

    def test_the_order_the_routes_are_given_in_does_not_matter(self):
        routes = {
            "A": route(severe=30), "B": route(severe=10), "C": route(severe=20),
        }
        for order in itertools.permutations(routes):
            result = recommend({rid: routes[rid] for rid in order})
            assert result.route_id == "B" and result.ranking == ("B", "C", "A")


# -------------------------------------------------------------------- strictly lexicographic


class TestNotABlendedScore:
    def test_one_severe_mile_loses_to_zero_however_slow_the_other_is(self):
        result = recommend({
            "fast": route(severe=1, minutes=300),
            "slow": route(severe=0, minutes=5000),
        })
        assert result.route_id == "slow"

    def test_zero_severe_wins_over_far_fewer_high_miles(self):
        result = recommend({
            "A": route(severe=0, high=900),
            "B": route(severe=1, high=0),
        })
        assert result.route_id == "A"

    def test_fewer_high_miles_wins_over_a_much_lower_average(self):
        result = recommend({
            "A": route(high=0, avg=3.9),
            "B": route(high=1, avg=0.0),
        })
        assert result.route_id == "A"

    def test_lower_average_wins_over_a_much_shorter_trip(self):
        result = recommend({
            "A": route(avg=0.01, minutes=9000),
            "B": route(avg=0.02, minutes=1),
        })
        assert result.route_id == "A"


# ------------------------------------------------------------------- ties use the rounded values


class TestRoundedTies:
    def test_severe_miles_that_round_alike_are_a_tie_and_time_decides(self):
        # 24.6 and 25.4 both show as 25 severe miles; unrounded, A would win on criterion 1.
        # Over 2,000 miles their average risk also shows alike (0.0369 and 0.0381 -> 0.04).
        a = built([(S, 24.6), (L, 1975.4)], minutes=700)
        b = built([(S, 25.4), (L, 1974.6)], minutes=650)
        assert (a.severe_miles, b.severe_miles) == (25, 25)
        assert (a.avg_risk, b.avg_risk) == (0.04, 0.04)
        result = recommend({"A": a, "B": b})
        assert (result.route_id, result.decided_by) == ("B", Criterion.DURATION)

    def test_a_half_mile_tie_rounds_up_for_both(self):
        a = built([(S, 24.5), (L, 1975.5)], minutes=700)
        b = built([(S, 25.4), (L, 1974.6)], minutes=650)
        assert (a.severe_miles, b.severe_miles) == (25, 25)
        assert (a.avg_risk, b.avg_risk) == (0.04, 0.04)
        assert recommend({"A": a, "B": b}).route_id == "B"

    def test_a_real_one_mile_difference_still_decides(self):
        a = built([(S, 24.4), (L, 975.6)], minutes=700)  # shows 24
        b = built([(S, 25.4), (L, 974.6)], minutes=650)  # shows 25
        result = recommend({"A": a, "B": b})
        assert (result.route_id, result.decided_by) == ("A", Criterion.SEVERE_MILES)

    def test_high_miles_round_alike_then_average_decides(self):
        a = built([(H, 40.4), (M, 100.0), (L, 859.6)], minutes=700)
        b = built([(H, 39.6), (M, 150.0), (L, 810.4)], minutes=650)
        assert (a.high_miles, b.high_miles) == (40, 40)
        assert a.avg_risk != b.avg_risk
        result = recommend({"A": a, "B": b})
        assert result.decided_by == Criterion.AVG_RISK
        assert result.route_id == "A"  # lower average

    def test_average_risk_that_rounds_alike_then_time_decides(self):
        # 331 / 1000 = 0.331 and 334 / 1000 = 0.334 both show as 0.33
        a = built([(M, 331.0), (L, 669.0)], minutes=700)
        b = built([(M, 334.0), (L, 666.0)], minutes=650)
        assert (a.avg_risk, b.avg_risk) == (0.33, 0.33)
        result = recommend({"A": a, "B": b})
        assert (result.route_id, result.decided_by) == ("B", Criterion.DURATION)

    def test_travel_times_that_round_to_the_same_minute_tie_completely(self):
        a = built([(L, 1000.0)], seconds=50_822)  # 847.03 min
        b = built([(L, 1000.0)], seconds=50_840)  # 847.33 min
        assert a.duration_minutes == b.duration_minutes == 847
        result = recommend({"A": a, "B": b})
        assert result.route_id == "A"  # listed first
        assert (result.decided_by, result.duration_delta_minutes) == (Criterion.DURATION, 0)

    def test_a_30_second_difference_can_make_a_whole_minute(self):
        a = built([(L, 1000.0)], seconds=50_849)  # 847.48 -> 847
        b = built([(L, 1000.0)], seconds=50_850)  # 847.5  -> 848
        assert recommend({"B": b, "A": a}).route_id == "A"


class TestFullTie:
    def test_the_route_listed_first_wins_and_duration_is_reported(self):
        same = route(severe=5, high=5, avg=1.0, minutes=600)
        result = recommend({"A": same, "B": same, "C": same})
        assert result.route_id == "A"
        assert result.decided_by == Criterion.DURATION
        assert result.versus_route_id == "B"
        assert result.duration_delta_minutes == 0
        assert result.ranking == ("A", "B", "C")

    def test_given_order_is_kept_among_equals_but_better_routes_move_up(self):
        same = route(severe=5)
        result = recommend({"A": same, "B": route(severe=9), "C": same})
        assert result.ranking == ("A", "C", "B")


# ------------------------------------------------------------------ who it is compared against


class TestComparedWithTheRunnerUp:
    def test_decided_by_is_about_the_runner_up_not_the_last_place(self):
        # A beats C on severe miles, but the runner-up B ties A there; A beats B on average risk.
        result = recommend({
            "A": route(severe=0, high=0, avg=0.10),
            "B": route(severe=0, high=0, avg=0.50),
            "C": route(severe=40, high=0, avg=0.90),
        })
        assert result.route_id == "A"
        assert result.versus_route_id == "B"
        assert result.decided_by == Criterion.AVG_RISK

    def test_the_delta_is_positive_when_the_winner_is_slower(self):
        result = recommend({
            "A": route(severe=0, minutes=860),
            "B": route(severe=25, minutes=840),
        })
        assert result.route_id == "A"
        assert result.duration_delta_minutes == 20

    def test_the_delta_is_negative_when_the_winner_is_faster(self):
        result = recommend({"A": route(severe=0, minutes=800), "B": route(severe=25, minutes=840)})
        assert result.duration_delta_minutes == -40

    def test_the_delta_is_in_displayed_minutes(self):
        a = built([(L, 1000.0)], seconds=50_849)  # shows 847
        b = built([(M, 1000.0)], seconds=50_850)  # shows 848
        result = recommend({"A": a, "B": b})
        assert result.duration_delta_minutes == a.duration_minutes - b.duration_minutes == -1


# ------------------------------------------------------------------------------ No Travel


class TestNoTravel:
    def test_a_no_travel_route_is_never_recommended_even_if_better_everywhere(self):
        result = recommend({
            "A": route(severe=0, high=0, avg=0.0, minutes=100, no_travel=True),
            "B": route(severe=50, high=50, avg=2.0, minutes=900),
        })
        assert result.route_id == "B"
        assert result.excluded_route_ids == ("A",)
        assert result.ranking == ("B",)

    def test_the_only_one_left_is_the_only_candidate(self):
        result = recommend({
            "A": route(no_travel=True),
            "B": route(severe=50),
            "C": route(no_travel=True),
        })
        assert result.route_id == "B"
        assert result.decided_by == Criterion.ONLY_CANDIDATE
        assert result.versus_route_id is None
        assert result.duration_delta_minutes is None
        assert result.excluded_route_ids == ("A", "C")

    def test_two_left_are_compared_normally(self):
        result = recommend({
            "A": route(severe=5),
            "B": route(no_travel=True),
            "C": route(severe=1),
        })
        assert (result.route_id, result.versus_route_id) == ("C", "A")
        assert result.decided_by == Criterion.SEVERE_MILES
        assert result.excluded_route_ids == ("B",)
        assert result.ranking == ("C", "A")

    def test_all_routes_no_travel_means_no_recommendation(self):
        result = recommend({"A": route(no_travel=True), "B": route(no_travel=True), "C": route(no_travel=True)})
        assert result == Recommendation(
            route_id=None,
            decided_by=None,
            versus_route_id=None,
            duration_delta_minutes=None,
            excluded_route_ids=("A", "B", "C"),
            ranking=(),
        )

    def test_a_single_route_with_no_travel(self):
        result = recommend({"A": route(no_travel=True)})
        assert result.route_id is None and result.excluded_route_ids == ("A",)

    def test_flag_comes_from_the_stretches_end_to_end(self):
        clean = built([(S, 200.0), (L, 800.0)])
        blocked = built([(L, 990.0), (N, 10.0)])
        result = recommend({"blocked": blocked, "clean": clean})
        assert result.route_id == "clean" and result.excluded_route_ids == ("blocked",)


# ---------------------------------------------------------------------------- fewer routes


class TestFewerThanThreeRoutes:
    def test_a_single_route_is_recommended_as_the_only_candidate(self):
        result = recommend({"A": route(severe=500, high=500, avg=3.0)})
        assert result.route_id == "A"
        assert result.decided_by == Criterion.ONLY_CANDIDATE
        assert result.versus_route_id is None and result.duration_delta_minutes is None
        assert result.excluded_route_ids == () and result.ranking == ("A",)

    def test_two_routes(self):
        result = recommend({"A": route(severe=3), "B": route(severe=2)})
        assert (result.route_id, result.versus_route_id) == ("B", "A")

    def test_no_routes_is_an_error(self):
        with pytest.raises(ValueError, match="no route"):
            recommend({})


# ------------------------------------------------------------------ against a plain reference


def reference_winner(routes):
    """The obvious reading of the rule: the smallest (severe, high, avg, minutes) tuple."""
    candidates = [(rid, r) for rid, r in routes.items() if not r.has_no_travel]
    if not candidates:
        return None
    best = min(candidates, key=lambda item: (item[1].severe_miles, item[1].high_miles, item[1].avg_risk, item[1].duration_minutes))
    return best[0]


class TestAgainstReference:
    def test_random_routes_with_many_ties(self):
        rng = random.Random(2026)
        for _ in range(3000):
            routes = {
                rid: route(
                    severe=rng.choice([0, 0, 5, 5, 20]),
                    high=rng.choice([0, 10, 10, 30]),
                    avg=rng.choice([0.0, 0.5, 0.5, 1.25]),
                    minutes=rng.choice([600, 600, 650, 700]),
                    no_travel=rng.random() < 0.2,
                )
                for rid in "ABC"[: rng.randint(1, 3)]
            }
            result = recommend(routes)
            assert result.route_id == reference_winner(routes), routes
            assert set(result.ranking) | set(result.excluded_route_ids) == set(routes)
            assert not set(result.ranking) & set(result.excluded_route_ids)

    def test_the_ranking_is_ordered_by_the_four_values(self):
        rng = random.Random(5)
        for _ in range(500):
            routes = {rid: route(severe=rng.randint(0, 3), high=rng.randint(0, 3), avg=rng.choice([0.1, 0.2]), minutes=rng.randint(1, 3)) for rid in "ABC"}
            keys = [(routes[r].severe_miles, routes[r].high_miles, routes[r].avg_risk, routes[r].duration_minutes) for r in recommend(routes).ranking]
            assert keys == sorted(keys)

    def test_decided_by_names_the_first_difference(self):
        rng = random.Random(11)
        names = [Criterion.SEVERE_MILES, Criterion.HIGH_MILES, Criterion.AVG_RISK, Criterion.DURATION]
        for _ in range(1000):
            routes = {rid: route(severe=rng.randint(0, 2), high=rng.randint(0, 2), avg=rng.choice([0.1, 0.2]), minutes=rng.randint(1, 2)) for rid in "AB"}
            result = recommend(routes)
            w, v = routes[result.route_id], routes[result.versus_route_id]
            wk = (w.severe_miles, w.high_miles, w.avg_risk, w.duration_minutes)
            vk = (v.severe_miles, v.high_miles, v.avg_risk, v.duration_minutes)
            expected = next((n for n, a, b in zip(names, wk, vk) if a != b), Criterion.DURATION)
            assert result.decided_by == expected


def test_decided_by_values_are_the_api_strings():
    assert [c.value for c in Criterion] == ["severe_miles", "high_miles", "avg_risk", "duration", "only_candidate"]
    assert str(Criterion.AVG_RISK) == "avg_risk"
