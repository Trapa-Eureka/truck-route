"""Unit tests for the risk rules and load rules (CLAUDE.md sections 3 and 4)."""

import itertools
import math

import pytest

from trip.risk import (
    RiskLevel,
    apply_load_rules,
    assess_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
)

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


# --------------------------------------------------------------------------------------
# Risk level
# --------------------------------------------------------------------------------------


def test_levels_are_ordered_low_to_no_travel():
    assert LOW < MODERATE < HIGH < SEVERE < NO_TRAVEL


def test_level_integers_match_the_average_risk_scale_and_heatmap_levels():
    assert [int(level) for level in RiskLevel] == [0, 1, 2, 3, 4]


def test_api_names_are_lowercase_with_underscore():
    assert [level.api_name for level in RiskLevel] == [
        "low",
        "moderate",
        "high",
        "severe",
        "no_travel",
    ]


# --------------------------------------------------------------------------------------
# Wind: <25 / 25-34 / 35-44 / 45-54 / >=55 mph
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wind_mph", "expected"),
    [
        (0, LOW),
        (24.99, LOW),
        (25, MODERATE),  # boundary 25
        (30, MODERATE),
        (34, MODERATE),
        (34.5, MODERATE),  # between the table's "34" and "35"
        (34.99, MODERATE),
        (35, HIGH),  # boundary 35
        (40, HIGH),
        (44, HIGH),
        (44.5, HIGH),
        (44.99, HIGH),
        (45, SEVERE),  # boundary 45
        (50, SEVERE),
        (54, SEVERE),
        (54.5, SEVERE),
        (54.99, SEVERE),
        (55, NO_TRAVEL),  # boundary 55
        (55.01, NO_TRAVEL),
        (80, NO_TRAVEL),
        (200, NO_TRAVEL),
    ],
)
def test_wind_levels(wind_mph, expected):
    assert classify_wind(wind_mph) == expected


# --------------------------------------------------------------------------------------
# Rain: <0.10 / 0.10-0.25 / 0.25-0.50 / 0.50-1.00 / >1.00 in/hr
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rain_in_hr", "expected"),
    [
        (0, LOW),
        (0.05, LOW),
        (0.099, LOW),
        (0.10, MODERATE),  # "< 0.10" is Low, so 0.10 is Moderate
        (0.20, MODERATE),
        (0.249, MODERATE),
        (0.25, HIGH),  # shared end of two ranges goes to the higher level
        (0.40, HIGH),
        (0.499, HIGH),
        (0.50, SEVERE),  # shared end of two ranges goes to the higher level
        (0.75, SEVERE),
        (0.999, SEVERE),
        (1.00, SEVERE),  # No Travel is strictly "> 1.00"
        (1.001, NO_TRAVEL),
        (1.01, NO_TRAVEL),
        (5, NO_TRAVEL),
    ],
)
def test_rain_levels(rain_in_hr, expected):
    assert classify_rain(rain_in_hr) == expected


# --------------------------------------------------------------------------------------
# Snow: <0.5 / 0.5-1.0 / 1.0-2.0 / 2.0-3.0 / >3.0 in/hr
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("snow_in_hr", "expected"),
    [
        (0, LOW),
        (0.25, LOW),
        (0.499, LOW),
        (0.5, MODERATE),  # "< 0.5" is Low, so 0.5 is Moderate
        (0.75, MODERATE),
        (0.999, MODERATE),
        (1.0, HIGH),  # shared end of two ranges goes to the higher level
        (1.5, HIGH),
        (1.999, HIGH),
        (2.0, SEVERE),  # shared end of two ranges goes to the higher level
        (2.5, SEVERE),
        (2.999, SEVERE),
        (3.0, SEVERE),  # No Travel is strictly "> 3.0"
        (3.001, NO_TRAVEL),
        (3.1, NO_TRAVEL),
        (10, NO_TRAVEL),
    ],
)
def test_snow_levels(snow_in_hr, expected):
    assert classify_snow(snow_in_hr) == expected


# --------------------------------------------------------------------------------------
# Classification is monotonic: more of a condition never lowers the level.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("classify", "step", "top"),
    [(classify_wind, 0.5, 70.0), (classify_rain, 0.01, 1.5), (classify_snow, 0.05, 4.0)],
)
def test_classification_never_decreases_as_the_value_grows(classify, step, top):
    previous = LOW
    for i in range(int(top / step) + 1):
        level = classify(round(i * step, 10))
        assert level >= previous, f"level dropped at {i * step}"
        previous = level
    assert previous == NO_TRAVEL


# --------------------------------------------------------------------------------------
# Invalid measurements are errors, never quietly 0
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("classify", [classify_wind, classify_rain, classify_snow])
@pytest.mark.parametrize(
    "bad", [None, float("nan"), math.inf, -math.inf, -0.1, -1, True, "12", [5]]
)
def test_classifiers_reject_invalid_values(classify, bad):
    with pytest.raises(ValueError):
        classify(bad)


@pytest.mark.parametrize(
    ("wind", "load"),
    [(None, 1000), (20, None), (float("nan"), 1000), (20, float("inf")), (20, -1), (-1, 100)],
)
def test_load_rules_reject_invalid_values(wind, load):
    with pytest.raises(ValueError):
        apply_load_rules(LOW, wind, load)


# --------------------------------------------------------------------------------------
# Load rules
#   wind >= 55                       -> No Travel (any load)
#   wind 45-54 and load > 30,000 lb  -> No Travel
#   wind 35-44 and load > 40,000 lb  -> Severe
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("load", [0, 1, 30_000, 40_000, 80_000, 200_000])
@pytest.mark.parametrize("wind", [55, 55.01, 60, 100])
def test_wind_55_or_more_is_no_travel_for_any_load(wind, load):
    assert assess_checkpoint(wind, 0, 0, load).level == NO_TRAVEL
    assert apply_load_rules(LOW, wind, load) == NO_TRAVEL


@pytest.mark.parametrize("wind", [45, 50, 54, 54.99])
def test_wind_45_to_54_with_load_above_30000_is_no_travel(wind):
    assert apply_load_rules(SEVERE, wind, 30_001) == NO_TRAVEL
    assert assess_checkpoint(wind, 0, 0, 30_001).level == NO_TRAVEL
    assert assess_checkpoint(wind, 0, 0, 45_000).level == NO_TRAVEL


@pytest.mark.parametrize("wind", [45, 50, 54, 54.99])
def test_wind_45_to_54_with_load_at_or_below_30000_stays_severe(wind):
    # exactly 30,000 lb does not trigger the rule (strictly greater-than), and the rule
    # never lowers the base Severe level either
    for load in (0, 15_000, 29_999.99, 30_000):
        risk = assess_checkpoint(wind, 0, 0, load)
        assert risk.level == SEVERE
        assert risk.load_escalated is False


@pytest.mark.parametrize("wind", [35, 40, 44, 44.99])
def test_wind_35_to_44_with_load_above_40000_is_severe(wind):
    risk = assess_checkpoint(wind, 0, 0, 40_001)
    assert risk.base_level == HIGH
    assert risk.level == SEVERE
    assert risk.load_escalated is True
    assert assess_checkpoint(wind, 0, 0, 80_000).level == SEVERE


@pytest.mark.parametrize("wind", [35, 40, 44, 44.99])
def test_wind_35_to_44_with_load_at_or_below_40000_stays_high(wind):
    # exactly 40,000 lb does not trigger the rule
    for load in (0, 30_001, 39_999.99, 40_000):
        risk = assess_checkpoint(wind, 0, 0, load)
        assert risk.level == HIGH
        assert risk.load_escalated is False


@pytest.mark.parametrize("wind", [0, 10, 24.99, 25, 30, 34, 34.5, 34.99])
def test_wind_below_35_is_not_affected_by_load(wind):
    heavy = assess_checkpoint(wind, 0, 0, 200_000)
    light = assess_checkpoint(wind, 0, 0, 0)
    assert heavy.level == light.level == classify_wind(wind)
    assert heavy.load_escalated is False


def test_load_rule_thresholds_are_strict_at_the_exact_numbers():
    # 30,000 lb: no rule at 45 mph, rule at one pound more
    assert assess_checkpoint(45, 0, 0, 30_000).level == SEVERE
    assert assess_checkpoint(45, 0, 0, 30_000.01).level == NO_TRAVEL
    # 40,000 lb: no rule at 35 mph, rule at one pound more
    assert assess_checkpoint(35, 0, 0, 40_000).level == HIGH
    assert assess_checkpoint(35, 0, 0, 40_000.01).level == SEVERE
    # wind edges of the two ranges: 44.99 mph is the 35-44 rule, 45 mph the 45-54 rule
    assert assess_checkpoint(44.99, 0, 0, 35_000).level == HIGH
    assert assess_checkpoint(45, 0, 0, 35_000).level == NO_TRAVEL


@pytest.mark.parametrize("level", list(RiskLevel))
@pytest.mark.parametrize("wind", [0, 20, 34.99, 35, 44.99, 45, 54.99, 55, 80])
@pytest.mark.parametrize("load", [0, 30_000, 30_001, 40_000, 40_001, 100_000])
def test_a_load_rule_never_lowers_a_level(level, wind, load):
    assert apply_load_rules(level, wind, load) >= level


# --------------------------------------------------------------------------------------
# Checkpoint level = highest of wind / rain / snow, then the load rules
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wind", "rain", "snow", "expected_level"),
    [
        (0, 0, 0, LOW),
        (30, 0, 0, MODERATE),  # wind drives it
        (0, 0.3, 0, HIGH),  # rain drives it
        (0, 0, 2.5, SEVERE),  # snow drives it
        (30, 0.6, 0.6, SEVERE),  # rain is the highest of Moderate / Severe / Moderate
        (40, 0.1, 3.5, NO_TRAVEL),  # snow No Travel beats High wind and Moderate rain
        (20, 1.5, 0, NO_TRAVEL),  # rain No Travel with calm wind
        (60, 0, 0, NO_TRAVEL),  # wind No Travel with dry weather
        (30, 0.1, 0.5, MODERATE),  # three-way tie
    ],
)
def test_checkpoint_level_is_the_highest_of_the_three_conditions(wind, rain, snow, expected_level):
    risk = assess_checkpoint(wind, rain, snow, load_weight_lb=0)
    assert risk.level == expected_level
    assert risk.base_level == expected_level
    assert risk.level == max(risk.level_by.wind, risk.level_by.rain, risk.level_by.snow)
    assert risk.load_escalated is False


def test_level_by_reports_each_conditions_own_level():
    risk = assess_checkpoint(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0.6, load_weight_lb=10_000)
    assert risk.level_by.wind == HIGH
    assert risk.level_by.rain == HIGH
    assert risk.level_by.snow == MODERATE
    assert risk.level == HIGH


def test_load_rule_applies_on_top_of_the_highest_condition():
    # heavy load in 40 mph wind raises the base High to Severe
    risk = assess_checkpoint(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_weight_lb=45_000)
    assert (risk.base_level, risk.level, risk.load_escalated) == (HIGH, SEVERE, True)

    # snow is already High, wind is High: the load rule still raises the final level
    risk = assess_checkpoint(wind_mph=40, rain_in_hr=0, snow_in_hr=1.5, load_weight_lb=45_000)
    assert (risk.base_level, risk.level, risk.load_escalated) == (HIGH, SEVERE, True)


def test_load_escalated_is_false_when_the_weather_already_reached_that_level():
    # rain is Severe, so the load rule's Severe changes nothing
    risk = assess_checkpoint(wind_mph=40, rain_in_hr=0.6, snow_in_hr=0, load_weight_lb=45_000)
    assert (risk.base_level, risk.level, risk.load_escalated) == (SEVERE, SEVERE, False)

    # snow is already No Travel
    risk = assess_checkpoint(wind_mph=50, rain_in_hr=0, snow_in_hr=3.5, load_weight_lb=45_000)
    assert (risk.base_level, risk.level, risk.load_escalated) == (NO_TRAVEL, NO_TRAVEL, False)


def test_wind_55_is_no_travel_from_the_wind_table_not_from_the_load_rule():
    risk = assess_checkpoint(wind_mph=55, rain_in_hr=0, snow_in_hr=0, load_weight_lb=80_000)
    assert (risk.base_level, risk.level, risk.load_escalated) == (NO_TRAVEL, NO_TRAVEL, False)


def test_heavy_load_in_45_to_54_wind_escalates_severe_to_no_travel():
    risk = assess_checkpoint(wind_mph=50, rain_in_hr=0, snow_in_hr=0, load_weight_lb=35_000)
    assert (risk.base_level, risk.level, risk.load_escalated) == (SEVERE, NO_TRAVEL, True)


def test_final_level_is_never_below_the_base_level_across_a_grid():
    winds = [0, 24.99, 25, 34.99, 35, 44.99, 45, 54.99, 55]
    rains = [0, 0.1, 0.25, 0.5, 1.0, 1.01]
    snows = [0, 0.5, 1.0, 2.0, 3.0, 3.01]
    loads = [0, 30_000, 30_001, 40_000, 40_001]
    for wind, rain, snow, load in itertools.product(winds, rains, snows, loads):
        risk = assess_checkpoint(wind, rain, snow, load)
        assert risk.level >= risk.base_level
        assert risk.load_escalated == (risk.level > risk.base_level)
        assert risk.level == apply_load_rules(risk.base_level, wind, load)


def test_integer_inputs_are_accepted():
    risk = assess_checkpoint(wind_mph=45, rain_in_hr=0, snow_in_hr=0, load_weight_lb=31_000)
    assert risk.level == NO_TRAVEL


# ------------------------------------------------------------------------------- risk_score

from trip.risk import risk_score  # noqa: E402


def _score(wind=0.0, rain=0.0, snow=0.0, load=0.0):
    level = assess_checkpoint(wind, rain, snow, load).level
    return risk_score(wind, rain, snow, level), level


class TestRiskScore:
    def test_calm_is_zero(self):
        assert _score() == (0.0, RiskLevel.LOW)

    @pytest.mark.parametrize(
        "wind, expected",
        [(0, 0.0), (12.5, 0.5), (25, 1.0), (30, 1.5), (35, 2.0), (40, 2.5), (45, 3.0), (50, 3.5), (54.9, 3.99)],
    )
    def test_wind_is_placed_between_its_thresholds(self, wind, expected):
        assert _score(wind=wind)[0] == pytest.approx(expected, abs=0.01)

    @pytest.mark.parametrize("rain, expected", [(0.05, 0.5), (0.10, 1.0), (0.175, 1.5), (0.25, 2.0), (0.375, 2.5), (0.5, 3.0), (0.75, 3.5)])
    def test_rain_is_placed_between_its_thresholds(self, rain, expected):
        assert _score(rain=rain)[0] == pytest.approx(expected, abs=0.01)

    @pytest.mark.parametrize("snow, expected", [(0.25, 0.5), (0.5, 1.0), (0.75, 1.5), (1.0, 2.0), (1.5, 2.5), (2.0, 3.0), (2.5, 3.5)])
    def test_snow_is_placed_between_its_thresholds(self, snow, expected):
        assert _score(snow=snow)[0] == pytest.approx(expected, abs=0.01)

    def test_the_worst_condition_counts(self):
        assert _score(wind=12.5, rain=0.175, snow=0.0)[0] == pytest.approx(1.5, abs=0.01)
        assert _score(wind=40, rain=0.05, snow=0.1)[0] == pytest.approx(2.5, abs=0.01)

    def test_no_travel_is_exactly_four(self):
        for kwargs in ({"wind": 55}, {"wind": 80}, {"rain": 1.01}, {"snow": 3.1}):
            assert _score(**kwargs) == (4.0, RiskLevel.NO_TRAVEL)

    def test_the_exact_no_travel_edge_of_rain_and_snow_stays_in_severe(self):
        # rain 1.00 and snow 3.0 are Severe, not No Travel (CLAUDE.md section 3): the score must agree
        for kwargs in ({"rain": 1.00}, {"snow": 3.0}):
            score, level = _score(**kwargs)
            assert level == RiskLevel.SEVERE and 3.0 <= score < 4.0

    def test_a_load_rule_lifts_the_score_to_the_start_of_the_level(self):
        light, light_level = _score(wind=40, load=40_000)  # High, not over 40,000 lb
        heavy, heavy_level = _score(wind=40, load=40_001)  # Severe by the load rule
        assert light_level == RiskLevel.HIGH and light == pytest.approx(2.5, abs=0.01)
        assert heavy_level == RiskLevel.SEVERE and heavy == 3.0

    def test_a_load_rule_to_no_travel(self):
        assert _score(wind=50, load=30_001) == (4.0, RiskLevel.NO_TRAVEL)
        assert _score(wind=50, load=30_000)[1] == RiskLevel.SEVERE

    def test_the_whole_part_is_always_the_level(self):
        winds = [0, 5, 24.99, 25, 34.99, 35, 40, 44.99, 45, 50, 54.99, 55, 70]
        rains = [0, 0.05, 0.0999, 0.10, 0.2499, 0.25, 0.4999, 0.50, 1.00, 1.0001, 3]
        snows = [0, 0.4, 0.4999, 0.5, 0.9999, 1.0, 1.9999, 2.0, 3.0, 3.0001, 6]
        loads = [0, 30_000, 30_001, 40_000, 40_001, 90_000]
        for wind, rain, snow, load in itertools.product(winds, rains, snows, loads):
            score, level = _score(wind, rain, snow, load)
            assert 0.0 <= score <= 4.0
            assert int(score) == int(level), (wind, rain, snow, load, score, level)

    def test_it_never_goes_down_when_the_weather_gets_worse(self):
        for load in (0, 35_000, 50_000):
            for series in ("wind", "rain", "snow"):
                top = {"wind": 70, "rain": 2.0, "snow": 4.0}[series]
                previous = -1.0
                for i in range(0, 401):
                    score, _ = _score(**{series: top * i / 400}, load=load)
                    assert score >= previous - 1e-9, (series, load, i)
                    previous = score

    def test_light_wind_differences_show_up(self):
        # the point of the score: 5 mph and 20 mph are both "Low" but not the same weather
        assert _score(wind=5)[1] == _score(wind=20)[1] == RiskLevel.LOW
        assert _score(wind=20)[0] - _score(wind=5)[0] > 0.5

    @pytest.mark.parametrize("bad", [None, math.nan, -1.0, math.inf, "5", True])
    def test_a_bad_measurement_is_refused_not_scored_as_zero(self, bad):
        with pytest.raises(ValueError):
            risk_score(bad, 0.0, 0.0, RiskLevel.LOW)
        with pytest.raises(ValueError):
            risk_score(0.0, bad, 0.0, RiskLevel.LOW)
        with pytest.raises(ValueError):
            risk_score(0.0, 0.0, bad, RiskLevel.LOW)
