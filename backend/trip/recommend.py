"""Route recommendation (CLAUDE.md section 5).

The priorities are compared **in order, never blended into a score**: a later criterion is looked
at only when every earlier one is tied.

1. fewest Severe miles
2. fewest High miles
3. lowest average risk
4. shortest travel time

Pure: no Django, no network. Severe miles, High miles and the average risk are compared at full
precision (see ``summary.py``), so a route with fewer Severe miles always beats one with more,
however small the difference, and a later criterion can never overrule an earlier one. Travel
time is compared in whole minutes. Criterion 4 decides whenever the first three are equal, which
is the common case of calm weather: every route then has exactly 0 Severe miles, 0 High miles
and an average risk of 0.

A route with any No Travel checkpoint is excluded and never recommended. If every route has one,
nothing is recommended (this is a normal answer, not an error).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .summary import RouteSummary


class Criterion(StrEnum):
    """What decided the recommendation. The values are the API's ``decided_by`` strings."""

    SEVERE_MILES = "severe_miles"
    HIGH_MILES = "high_miles"
    AVG_RISK = "avg_risk"
    DURATION = "duration"
    ONLY_CANDIDATE = "only_candidate"


@dataclass(frozen=True)
class Recommendation:
    """The ``recommendation`` object of the API contract."""

    #: The recommended route, or ``None`` when every route has a No Travel checkpoint.
    route_id: str | None
    #: The first criterion on which the winner beats the runner-up; ``None`` without a winner.
    decided_by: Criterion | None
    #: The runner-up the winner is compared with; ``None`` with fewer than two candidates.
    versus_route_id: str | None
    #: Winner's minutes minus the runner-up's (positive = the winner is slower).
    duration_delta_minutes: int | None
    #: Routes left out because of No Travel, in the order they were given.
    excluded_route_ids: tuple[str, ...]
    #: The routes that are not excluded, best first.
    ranking: tuple[str, ...]


# The four criteria in priority order, each as the value read from a summary.
_CRITERIA = (
    (Criterion.SEVERE_MILES, lambda s: s.severe_miles),
    (Criterion.HIGH_MILES, lambda s: s.high_miles),
    (Criterion.AVG_RISK, lambda s: s.avg_risk),
    (Criterion.DURATION, lambda s: s.duration_minutes),
)


def _key(summary: RouteSummary) -> tuple:
    return tuple(read(summary) for _, read in _CRITERIA)


def _decided_by(winner: RouteSummary, runner_up: RouteSummary) -> Criterion:
    """The first criterion on which the two routes differ.

    If they tie on all four the answer is ``DURATION``: the route that is listed first wins and
    the comparison ended at the last criterion.
    """
    for criterion, read in _CRITERIA:
        if read(winner) != read(runner_up):
            return criterion
    return Criterion.DURATION


def recommend(summaries: Mapping[str, RouteSummary]) -> Recommendation:
    """Pick the best route. ``summaries`` maps route id to summary, in the routing API's order.

    That order breaks a tie on all four criteria (the first route listed wins).
    """
    if not summaries:
        raise ValueError("there is no route to recommend")

    excluded = tuple(rid for rid, s in summaries.items() if s.has_no_travel)
    # sorted() is stable, so equal keys stay in the order the routes were given.
    ranking = tuple(
        sorted(
            (rid for rid, s in summaries.items() if not s.has_no_travel),
            key=lambda rid: _key(summaries[rid]),
        )
    )

    if not ranking:
        return Recommendation(None, None, None, None, excluded, ranking)

    winner_id = ranking[0]
    if len(ranking) == 1:
        return Recommendation(winner_id, Criterion.ONLY_CANDIDATE, None, None, excluded, ranking)

    runner_up_id = ranking[1]
    winner, runner_up = summaries[winner_id], summaries[runner_up_id]
    return Recommendation(
        route_id=winner_id,
        decided_by=_decided_by(winner, runner_up),
        versus_route_id=runner_up_id,
        duration_delta_minutes=winner.duration_minutes - runner_up.duration_minutes,
        excluded_route_ids=excluded,
        ranking=ranking,
    )
