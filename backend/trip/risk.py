"""Weather risk rules and load rules (CLAUDE.md sections 3 and 4).

Everything here is a pure function of its inputs: no Django, no network, no clock.
Units are the ones the assignment's tables use: wind in mph, rain and snow in in/hr,
load weight in lb.

Boundary interpretation (CLAUDE.md section 3): weather values are continuous, so the
tables are read as gap-free intervals.

* Wind: ``<25 / 25-<35 / 35-<45 / 45-<55 / >=55``. A value such as 34.5 mph is Moderate.
* Rain and snow: a value where two ranges meet goes to the *higher* level (rain 0.25 is High,
  snow 2.0 is Severe), the same way "< 0.10 -> Low" makes 0.10 Moderate. No Travel applies
  only when the value is strictly greater than the limit, exactly as printed (> 1.00 rain,
  > 3.0 snow), so rain 1.00 and snow 3.0 are still Severe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    """Risk levels in ascending order.

    The integer values are used for the average-risk calculation (Low 0 ... No Travel 4)
    and are the integer levels sent in the heatmap response.
    """

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def api_name(self) -> str:
        """The lowercase string used in the API (``no_travel``, ``severe`` ...)."""
        return self.name.lower()


@dataclass(frozen=True)
class _Thresholds:
    """Where each level starts for one weather condition.

    ``moderate``, ``high`` and ``severe`` are inclusive lower bounds. ``no_travel`` is the
    No Travel limit; ``no_travel_inclusive`` says whether the limit itself is No Travel.
    """

    moderate: float
    high: float
    severe: float
    no_travel: float
    no_travel_inclusive: bool


# Wind in mph: "No Travel >= 55 mph", so 55 itself is No Travel.
WIND_THRESHOLDS = _Thresholds(25.0, 35.0, 45.0, 55.0, no_travel_inclusive=True)
# Rain in in/hr: "No Travel > 1.00", so 1.00 itself is Severe.
RAIN_THRESHOLDS = _Thresholds(0.10, 0.25, 0.50, 1.00, no_travel_inclusive=False)
# Snow in in/hr: "No Travel > 3.0", so 3.0 itself is Severe.
SNOW_THRESHOLDS = _Thresholds(0.5, 1.0, 2.0, 3.0, no_travel_inclusive=False)

# Load rules (section 4). Load comparisons are strictly greater-than.
WIND_LOAD_NO_TRAVEL_MIN_MPH = 45.0
LOAD_NO_TRAVEL_ABOVE_LB = 30_000.0
WIND_LOAD_SEVERE_MIN_MPH = 35.0
LOAD_SEVERE_ABOVE_LB = 40_000.0


def _require_measurement(value: object, name: str) -> float:
    """Return ``value`` as a float, rejecting anything that is not a real measurement.

    A missing value (``None``), NaN or infinity must never be quietly treated as 0, because
    that would make a stretch with unknown weather look safe.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if number < 0:
        raise ValueError(f"{name} must not be negative, got {value!r}")
    return number


def _classify(value: float, thresholds: _Thresholds) -> RiskLevel:
    if value > thresholds.no_travel or (
        thresholds.no_travel_inclusive and value == thresholds.no_travel
    ):
        return RiskLevel.NO_TRAVEL
    if value >= thresholds.severe:
        return RiskLevel.SEVERE
    if value >= thresholds.high:
        return RiskLevel.HIGH
    if value >= thresholds.moderate:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_wind(wind_mph: float) -> RiskLevel:
    """Base level for a wind speed in mph."""
    return _classify(_require_measurement(wind_mph, "wind_mph"), WIND_THRESHOLDS)


def classify_rain(rain_in_hr: float) -> RiskLevel:
    """Base level for a rain rate in in/hr."""
    return _classify(_require_measurement(rain_in_hr, "rain_in_hr"), RAIN_THRESHOLDS)


def classify_snow(snow_in_hr: float) -> RiskLevel:
    """Base level for a snowfall rate in in/hr."""
    return _classify(_require_measurement(snow_in_hr, "snow_in_hr"), SNOW_THRESHOLDS)


def apply_load_rules(level: RiskLevel, wind_mph: float, load_weight_lb: float) -> RiskLevel:
    """Raise ``level`` according to the load rules. A load rule never lowers a level.

    * wind >= 55 mph                    -> No Travel, for any load
    * wind 45-54 mph and load > 30,000  -> No Travel
    * wind 35-44 mph and load > 40,000  -> Severe
    """
    wind = _require_measurement(wind_mph, "wind_mph")
    load = _require_measurement(load_weight_lb, "load_weight_lb")

    if wind >= WIND_THRESHOLDS.no_travel:
        required = RiskLevel.NO_TRAVEL
    elif wind >= WIND_LOAD_NO_TRAVEL_MIN_MPH and load > LOAD_NO_TRAVEL_ABOVE_LB:
        required = RiskLevel.NO_TRAVEL
    elif wind >= WIND_LOAD_SEVERE_MIN_MPH and load > LOAD_SEVERE_ABOVE_LB:
        required = RiskLevel.SEVERE
    else:
        required = RiskLevel.LOW
    return max(level, required)


@dataclass(frozen=True)
class LevelBy:
    """Base level of each weather condition, before the load rules."""

    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel


@dataclass(frozen=True)
class CheckpointRisk:
    """The risk of one checkpoint (the ``level_by`` / ``level`` / ``load_escalated`` fields)."""

    level_by: LevelBy
    #: Highest of the three base levels, before the load rules.
    base_level: RiskLevel
    #: Final level: ``base_level`` raised by the load rules.
    level: RiskLevel
    #: True only when a load rule actually raised the level above ``base_level``.
    load_escalated: bool


def assess_checkpoint(
    wind_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_weight_lb: float,
) -> CheckpointRisk:
    """Final risk of a checkpoint.

    The level is the highest of the wind, rain and snow levels, then raised by the load
    rules. ``load_escalated`` is False when the load rule's level was already reached by
    the weather (for example heavy load in 40 mph wind while rain is already Severe).
    """
    level_by = LevelBy(
        wind=classify_wind(wind_mph),
        rain=classify_rain(rain_in_hr),
        snow=classify_snow(snow_in_hr),
    )
    base_level = max(level_by.wind, level_by.rain, level_by.snow)
    level = apply_load_rules(base_level, wind_mph, load_weight_lb)
    return CheckpointRisk(
        level_by=level_by,
        base_level=base_level,
        level=level,
        load_escalated=level > base_level,
    )
