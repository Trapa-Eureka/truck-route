"""Route summary: miles per risk level, average risk, travel time (CLAUDE.md section 5).

Pure: no Django, no network, no clock. The input is the list of *stretches* of a route: each
checkpoint's final risk level and the miles it stands for (``Checkpoint.represents_miles``).

The miles per level and the average risk are kept at **full precision** (only cleaned of
floating-point noise), and the recommendation compares exactly these values: 24.6 Severe miles
beat 25.4 although both read "25" on a card, and a Severe stretch of 0.2 miles is not zero.
Rounding to whole miles before comparing would let a later criterion overrule an earlier one.
The travel time is in whole minutes, the unit it is shown in. ``shown()`` rounds a value for
the API response without ever turning an amount above zero into 0 (CLAUDE.md section 5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from .risk import RiskLevel


@dataclass(frozen=True)
class Stretch:
    """A piece of route that has one risk level."""

    level: RiskLevel
    miles: float


@dataclass(frozen=True)
class RouteSummary:
    """One route's numbers. Miles per level and the average risk are at full precision."""

    #: Total distance, rounded to the mile (display only).
    distance_miles: int
    #: Travel time, rounded to the minute: what is shown and what criterion 4 compares.
    duration_minutes: int
    arrival: datetime
    miles_by_level: dict[RiskLevel, float]
    severe_miles: float
    high_miles: float
    avg_risk: float
    has_no_travel: bool


# Sums of floats carry noise in the last digits (0.1 + 0.2 = 0.30000000000000004). Six decimals
# of a mile are 1.6 mm: two routes that differ by less are equal.
_NOISE_DECIMALS = 6


def _clean(value: float) -> float:
    return round(value, _NOISE_DECIMALS) + 0.0


def round_half_up(value: float, decimals: int = 0) -> float:
    """Round with 0.5 going up (24.5 -> 25), the way a person rounds.

    Python's ``round`` goes to the even neighbour (24.5 -> 24, 2.5 -> 2), which would turn
    a tie on screen into a difference in the comparison. Sums of floats also carry noise
    (24.499999999999996 for a true 24.5), so the value is first cleaned to 6 decimals.
    Returns an ``int`` when ``decimals`` is 0.
    """
    exact = Decimal(repr(round(value, 6)))
    rounded = exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    return int(rounded) if decimals == 0 else float(rounded)


def shown(value: float, decimals: int) -> float:
    """``value`` rounded half up for the API, but an amount above zero never becomes 0.

    A Severe stretch of 0.004 miles is sent as 0.01, not 0: the screen may say "<1 mi", it must
    not say "0" or "All Low" for a route the recommendation ranked as having Severe miles.
    """
    rounded = round_half_up(value, decimals)
    if value > 0 and rounded == 0:
        return float(Decimal(1).scaleb(-decimals))
    return rounded


def summarize_route(
    stretches: Sequence[Stretch], duration_seconds: float, departure: datetime
) -> RouteSummary:
    """Summarize one route.

    ``stretches`` are the checkpoints' levels with the miles each stands for (they add up to
    the route's distance). ``duration_seconds`` is TomTom's travel time and ``departure`` must
    be timezone-aware.
    """
    if not stretches:
        raise ValueError("a route needs at least one stretch")
    for stretch in stretches:
        if not isinstance(stretch.level, RiskLevel):
            raise ValueError(f"stretch level must be a RiskLevel, got {stretch.level!r}")
        if not (math.isfinite(stretch.miles) and stretch.miles >= 0):
            raise ValueError(f"stretch miles must be finite and not negative: {stretch.miles!r}")
    if not (math.isfinite(duration_seconds) and duration_seconds >= 0):
        raise ValueError(f"duration_seconds must be finite and not negative: {duration_seconds!r}")
    if departure.tzinfo is None or departure.utcoffset() is None:
        raise ValueError("departure must be timezone-aware")

    miles_by_level = {level: 0.0 for level in RiskLevel}
    for stretch in stretches:
        miles_by_level[stretch.level] += stretch.miles
    distance = sum(miles_by_level.values())
    if distance <= 0:
        raise ValueError("a route needs a distance above zero")

    # Average of the level numbers (Low 0 ... No Travel 4) weighted by stretch length.
    average = sum(int(level) * miles for level, miles in miles_by_level.items()) / distance

    # Same rounding as the checkpoint ETAs, so the arrival equals the last checkpoint's ETA.
    arrival = departure.astimezone(timezone.utc) + timedelta(seconds=round(duration_seconds))

    return RouteSummary(
        distance_miles=round_half_up(distance),
        duration_minutes=round_half_up(duration_seconds / 60),
        arrival=arrival,
        miles_by_level={level: _clean(m) for level, m in miles_by_level.items()},
        severe_miles=_clean(miles_by_level[RiskLevel.SEVERE]),
        high_miles=_clean(miles_by_level[RiskLevel.HIGH]),
        avg_risk=_clean(average),
        has_no_travel=any(s.level == RiskLevel.NO_TRAVEL for s in stretches),
    )
