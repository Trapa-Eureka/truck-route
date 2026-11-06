"""Unit tests for checkpoint sampling and ETA (CLAUDE.md sections 2, 5 and 7)."""

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trip.sampling import (
    EARTH_RADIUS_M,
    MAX_CHECKPOINTS,
    METERS_PER_MILE,
    Anchor,
    build_checkpoints,
    checkpoint_miles,
    haversine_m,
    represented_miles,
)

UTC = timezone.utc
DEPARTURE = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "fixtures" / "tomtom_route_prefix.json"


def meridian_route(total_miles, n_points=101, lat0=38.0, lon=-90.0):
    """Points along a meridian. Haversine along a meridian is exact, so the length is known."""
    span_deg = math.degrees(total_miles * METERS_PER_MILE / EARTH_RADIUS_M)
    return [(lat0 + span_deg * i / (n_points - 1), lon) for i in range(n_points)]


def meridian_lat(total_miles, mile, lat0=38.0):
    return lat0 + math.degrees(mile * METERS_PER_MILE / EARTH_RADIUS_M)


def route_length_m(points):
    return sum(haversine_m(*a, *b) for a, b in zip(points, points[1:]))


def seconds_after_departure(checkpoint, departure=DEPARTURE):
    return (checkpoint.eta - departure).total_seconds()


# --------------------------------------------------------------------------------------
# haversine
# --------------------------------------------------------------------------------------


def test_haversine_known_distances():
    assert haversine_m(40, -90, 40, -90) == 0
    one_degree = math.radians(1) * EARTH_RADIUS_M
    assert haversine_m(40, -90, 41, -90) == pytest.approx(one_degree)
    assert haversine_m(0, 10, 0, 11) == pytest.approx(one_degree)
    # symmetric
    assert haversine_m(41.88, -87.63, 39.74, -104.98) == pytest.approx(
        haversine_m(39.74, -104.98, 41.88, -87.63)
    )


# --------------------------------------------------------------------------------------
# Where checkpoints go: origin, every interval, destination
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (100, 25, [0, 25, 50, 75, 100]),  # destination exactly on an interval: not listed twice
        (101, 25, [0, 25, 50, 75, 100, 101]),  # not divisible: a short last stretch
        (60, 25, [0, 25, 50, 60]),
        (8, 25, [0, 8]),  # shorter than the interval: origin and destination only
        (25, 25, [0, 25]),  # exactly one interval
        (25.5, 25, [0, 25, 25.5]),
        (0.5, 10, [0, 0.5]),
        (100, 10, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        (100, 50, [0, 50, 100]),
        (130, 50, [0, 50, 100, 130]),
    ],
)
def test_checkpoint_miles(total, interval, expected):
    assert checkpoint_miles(total, interval) == pytest.approx(expected)


@pytest.mark.parametrize(
    "total",
    [
        160934.4 / METERS_PER_MILE,  # 100 miles converted back from meters
        math.nextafter(100, 200),  # the next float above 100
        100 + 1e-12,
        100 + 5e-7,  # still inside the 1e-6 mile tolerance
    ],
)
def test_a_destination_a_float_hair_past_an_interval_is_not_listed_twice(total):
    miles = checkpoint_miles(total, 25)
    assert len(miles) == 5
    assert miles[-1] == pytest.approx(100)


def test_a_destination_beyond_the_tolerance_is_its_own_checkpoint():
    assert len(checkpoint_miles(100 + 1e-3, 25)) == 6


@pytest.mark.parametrize("interval", [10, 25, 50])
@pytest.mark.parametrize("total", [0.3, 9.99, 10, 10.01, 24.9, 25, 49.99, 50, 51, 137.3, 999.9, 1336.1])
def test_checkpoint_miles_invariants(total, interval):
    miles = checkpoint_miles(total, interval)
    assert miles[0] == 0
    assert miles[-1] == pytest.approx(total)
    gaps = [b - a for a, b in zip(miles, miles[1:])]
    assert all(gap > 0 for gap in gaps)
    assert all(gap == pytest.approx(interval) for gap in gaps[:-1])
    assert 0 < gaps[-1] <= interval + 1e-9
    assert len(miles) == math.ceil(total / interval - 1e-9) + 1


@pytest.mark.parametrize("total", [0, -5, float("nan"), float("inf")])
def test_checkpoint_miles_rejects_a_route_without_a_usable_length(total):
    # inf used to loop for ever
    with pytest.raises(ValueError):
        checkpoint_miles(total, 25)


@pytest.mark.parametrize("interval", [0, -10, float("nan"), float("inf")])
def test_checkpoint_miles_rejects_a_bad_interval(interval):
    with pytest.raises(ValueError):
        checkpoint_miles(100, interval)


def test_checkpoint_miles_refuses_an_interval_that_would_need_too_many_checkpoints():
    # a tiny interval used to loop for ever
    with pytest.raises(ValueError, match="checkpoints"):
        checkpoint_miles(1000, 1e-9)
    with pytest.raises(ValueError, match="checkpoints"):
        checkpoint_miles(MAX_CHECKPOINTS + 1, 1)
    assert len(checkpoint_miles(MAX_CHECKPOINTS, 1)) == MAX_CHECKPOINTS + 1  # exactly at the limit


# --------------------------------------------------------------------------------------
# Miles each checkpoint stands for: midpoint to midpoint
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("miles", "expected"),
    [
        ([0, 25, 50, 75, 100], [12.5, 25, 25, 25, 12.5]),
        ([0, 25, 50, 60], [12.5, 25, 17.5, 5]),
        ([0, 8], [4, 4]),
        ([0, 100], [50, 50]),
    ],
)
def test_represented_miles(miles, expected):
    assert represented_miles(miles) == pytest.approx(expected)


@pytest.mark.parametrize("interval", [10, 25, 50])
@pytest.mark.parametrize("total", [0.3, 8, 10, 24.9, 25, 51, 99.99, 100, 137.3, 1336.1])
def test_represented_miles_add_up_to_the_route_length(total, interval):
    miles = checkpoint_miles(total, interval)
    stands_for = represented_miles(miles)
    assert len(stands_for) == len(miles)
    assert all(length > 0 for length in stands_for)
    assert sum(stands_for) == pytest.approx(total, abs=1e-9)


# --------------------------------------------------------------------------------------
# Positions and ETAs on a route with a known speed profile
#   first 50 miles at 60 mph (3000 s), last 50 miles at 30 mph (6000 s)
# --------------------------------------------------------------------------------------

TOTAL_MILES = 100
TOTAL_M = TOTAL_MILES * METERS_PER_MILE
TOTAL_S = 9000


def profile_route(n_points=101):
    points = meridian_route(TOTAL_MILES, n_points)
    mid = (n_points - 1) // 2
    anchors = [Anchor(mid, 50 * METERS_PER_MILE, 3000)]
    return points, anchors


def test_etas_follow_the_speed_profile():
    points, anchors = profile_route()
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, DEPARTURE, 25)
    assert [cp.mile for cp in cps] == pytest.approx([0, 25, 50, 75, 100])
    # 25 mi at 60 mph = 1500 s; 50 mi = 3000 s; then 30 mph: +1500 s per 25 mi... = 6000, 9000
    assert [seconds_after_departure(cp) for cp in cps] == [0, 1500, 3000, 6000, 9000]


def test_positions_follow_the_route():
    points, anchors = profile_route()
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, DEPARTURE, 25)
    for cp in cps:
        assert cp.lat == pytest.approx(meridian_lat(TOTAL_MILES, cp.mile), abs=1e-6)
        assert cp.lon == pytest.approx(-90.0)
    assert (cps[0].lat, cps[0].lon) == points[0]
    assert (cps[-1].lat, cps[-1].lon) == pytest.approx(points[-1])


def test_represented_miles_and_indexes_are_filled_in():
    points, anchors = profile_route()
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, DEPARTURE, 25)
    assert [cp.index for cp in cps] == [0, 1, 2, 3, 4]
    assert [cp.represents_miles for cp in cps] == pytest.approx([12.5, 25, 25, 25, 12.5])
    assert sum(cp.represents_miles for cp in cps) == pytest.approx(TOTAL_MILES)


def test_first_checkpoint_is_the_departure_and_last_is_the_arrival():
    points, anchors = profile_route()
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, DEPARTURE, 10)
    assert cps[0].eta == DEPARTURE
    assert cps[-1].eta == DEPARTURE + timedelta(seconds=TOTAL_S)


@pytest.mark.parametrize("interval", [10, 25, 50])
@pytest.mark.parametrize("total_miles", [0.5, 7, 24.9, 25, 25.1, 49, 50, 99.99, 100, 101, 137.3, 1000])
def test_invariants_on_a_uniform_route(total_miles, interval):
    points = meridian_route(total_miles, 201)
    total_m = total_miles * METERS_PER_MILE
    total_s = total_miles * 60  # 60 s per mile
    cps = build_checkpoints(points, [], total_m, total_s, DEPARTURE, interval)

    assert cps[0].mile == 0 and cps[0].eta == DEPARTURE
    assert cps[-1].mile == pytest.approx(total_miles)
    assert cps[-1].eta == DEPARTURE + timedelta(seconds=round(total_s))
    assert sum(cp.represents_miles for cp in cps) == pytest.approx(total_miles, abs=1e-9)
    assert [cp.mile for cp in cps] == sorted(set(cp.mile for cp in cps))  # strictly increasing
    etas = [cp.eta for cp in cps]
    assert etas == sorted(etas)
    for cp in cps:  # uniform speed: ETA is proportional to the mile
        assert seconds_after_departure(cp) == pytest.approx(cp.mile * 60, abs=1)


def test_a_route_shorter_than_the_interval_has_origin_and_destination_only():
    points = meridian_route(8)
    cps = build_checkpoints(points, [], 8 * METERS_PER_MILE, 600, DEPARTURE, 25)
    assert [cp.mile for cp in cps] == pytest.approx([0, 8])
    assert [cp.represents_miles for cp in cps] == pytest.approx([4, 4])
    assert cps[1].eta == DEPARTURE + timedelta(seconds=600)


def test_a_destination_on_an_interval_is_a_single_checkpoint():
    points = meridian_route(100)
    cps = build_checkpoints(points, [], 100 * METERS_PER_MILE, 6000, DEPARTURE, 25)
    assert len(cps) == 5
    assert cps[-1].mile == pytest.approx(100)


def test_a_route_not_divisible_by_the_interval_ends_with_a_short_stretch():
    points = meridian_route(101)
    cps = build_checkpoints(points, [], 101 * METERS_PER_MILE, 6060, DEPARTURE, 25)
    assert [cp.mile for cp in cps] == pytest.approx([0, 25, 50, 75, 100, 101])
    # 100.5 is the midpoint between the last two, so the destination stands for half a mile
    assert cps[-1].represents_miles == pytest.approx(0.5)
    assert cps[-2].represents_miles == pytest.approx(12.5 + 0.5)


# --------------------------------------------------------------------------------------
# Anchors define where TomTom's distances and times apply
# --------------------------------------------------------------------------------------


def test_a_checkpoint_on_an_anchors_distance_lands_exactly_on_that_anchors_point():
    # TomTom's length is 0.2% longer than the polyline's own length, as on real routes
    points = meridian_route(100)
    official_total_m = route_length_m(points) * 1.002
    anchor = Anchor(50, official_total_m / 2, 3000)
    cps = build_checkpoints(points, [anchor], official_total_m, 9000, DEPARTURE, official_total_m / 2 / METERS_PER_MILE)
    assert [cp.mile for cp in cps] == pytest.approx([0, official_total_m / 2 / METERS_PER_MILE, official_total_m / METERS_PER_MILE])
    assert (cps[1].lat, cps[1].lon) == pytest.approx(points[50], abs=1e-9)
    assert seconds_after_departure(cps[1]) == 3000


def test_without_anchors_time_is_proportional_to_distance():
    points = meridian_route(100)
    cps = build_checkpoints(points, [], TOTAL_M, 7200, DEPARTURE, 25)
    assert [seconds_after_departure(cp) for cp in cps] == [0, 1800, 3600, 5400, 7200]


def test_anchors_given_out_of_order_give_the_same_result():
    points = meridian_route(100)
    anchors = [Anchor(25, 25 * METERS_PER_MILE, 1000), Anchor(50, 50 * METERS_PER_MILE, 3000), Anchor(75, 75 * METERS_PER_MILE, 4000)]
    ordered = build_checkpoints(points, anchors, TOTAL_M, 9000, DEPARTURE, 10)
    shuffled = build_checkpoints(points, [anchors[2], anchors[0], anchors[1]], TOTAL_M, 9000, DEPARTURE, 10)
    assert ordered == shuffled


def test_anchors_sharing_a_point_index_keep_the_first():
    points = meridian_route(100)
    first = Anchor(50, 50 * METERS_PER_MILE, 3000)
    second = Anchor(50, 50 * METERS_PER_MILE + 100, 3003)  # same spot, like TomTom's duplicate instructions
    both = build_checkpoints(points, [first, second], TOTAL_M, 9000, DEPARTURE, 25)
    only_first = build_checkpoints(points, [first], TOTAL_M, 9000, DEPARTURE, 25)
    assert both == only_first


def test_a_stop_gives_the_arrival_time_and_time_continues_after_it():
    # The truck reaches mile 50 at 3000 s and is still there at 3600 s (two anchors, same distance).
    # A checkpoint at mile 50 gets the time it first arrives; later checkpoints continue from 3600 s.
    points = meridian_route(100)
    stop = [Anchor(50, 50 * METERS_PER_MILE, 3000), Anchor(51, 50 * METERS_PER_MILE, 3600)]
    cps = build_checkpoints(points, stop, TOTAL_M, 9000, DEPARTURE, 25)
    assert [cp.mile for cp in cps] == pytest.approx([0, 25, 50, 75, 100])
    assert [seconds_after_departure(cp) for cp in cps] == [0, 1500, 3000, 6300, 9000]


def test_the_ends_are_pinned_to_the_route_totals():
    points = meridian_route(100)
    # wrong values at both ends are replaced by (0 m, 0 s) and (total length, total time)
    anchors = [Anchor(0, 5000, 500), Anchor(100, 90 * METERS_PER_MILE, 8000)]
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, DEPARTURE, 25)
    assert cps[0].eta == DEPARTURE
    assert cps[-1].eta == DEPARTURE + timedelta(seconds=TOTAL_S)


@pytest.mark.parametrize(
    "anchors",
    [
        [Anchor(30, 30 * METERS_PER_MILE, 2000), Anchor(60, 60 * METERS_PER_MILE, 1500)],  # time goes backwards
        [Anchor(30, 40 * METERS_PER_MILE, 2000), Anchor(60, 35 * METERS_PER_MILE, 3000)],  # distance goes backwards
        [Anchor(50, 150 * METERS_PER_MILE, 3000)],  # farther than the whole route
        [Anchor(50, 50 * METERS_PER_MILE, 99_999)],  # later than the whole trip
    ],
)
def test_inconsistent_anchors_are_rejected(anchors):
    with pytest.raises(ValueError):
        build_checkpoints(meridian_route(100), anchors, TOTAL_M, TOTAL_S, DEPARTURE, 25)


@pytest.mark.parametrize("index", [-1, 101, 5000])
def test_an_anchor_outside_the_route_is_rejected(index):
    with pytest.raises(ValueError):
        build_checkpoints(meridian_route(100), [Anchor(index, 1000, 100)], TOTAL_M, TOTAL_S, DEPARTURE, 25)


# --------------------------------------------------------------------------------------
# Time zones: the departure is an instant, ETAs are UTC
# --------------------------------------------------------------------------------------


def test_a_naive_departure_is_rejected():
    points, anchors = profile_route()
    with pytest.raises(ValueError, match="timezone-aware"):
        build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, datetime(2026, 11, 9, 14, 0), 25)


@pytest.mark.parametrize(
    "departure",
    [
        datetime(2026, 11, 9, 8, 0, tzinfo=timezone(timedelta(hours=-6))),  # Chicago, CST
        datetime(2026, 11, 9, 7, 0, tzinfo=timezone(timedelta(hours=-7))),  # Denver, MST
        datetime(2026, 11, 9, 23, 0, tzinfo=timezone(timedelta(hours=9))),  # Seoul
    ],
)
def test_the_same_instant_in_any_offset_gives_the_same_utc_etas(departure):
    points, anchors = profile_route()
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, departure, 25)
    assert all(cp.eta.tzinfo == UTC for cp in cps)
    assert cps[0].eta == datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
    assert cps[-1].eta == datetime(2026, 11, 9, 14, 0, tzinfo=UTC) + timedelta(seconds=TOTAL_S)


def test_etas_cross_midnight_and_a_dst_change_correctly():
    # 2026-11-01 is the US fall-back date; elapsed time is absolute, so ETAs stay exact in UTC
    departure = datetime(2026, 10, 31, 22, 0, tzinfo=timezone(timedelta(hours=-5)))  # CDT
    points, anchors = profile_route()
    cps = build_checkpoints(points, anchors, TOTAL_M, TOTAL_S, departure, 25)
    assert cps[0].eta == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    assert cps[-1].eta == datetime(2026, 11, 1, 3, 0, tzinfo=UTC) + timedelta(seconds=TOTAL_S)


# --------------------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("points", [[], [(40.0, -90.0)]])
def test_a_route_needs_two_points(points):
    with pytest.raises(ValueError):
        build_checkpoints(points, [], TOTAL_M, TOTAL_S, DEPARTURE, 25)


@pytest.mark.parametrize("bad", [(float("nan"), -90.0), (40.0, float("inf")), (91.0, 0.0), (0.0, 181.0)])
def test_bad_coordinates_are_rejected(bad):
    with pytest.raises(ValueError):
        build_checkpoints([(40.0, -90.0), bad], [], TOTAL_M, TOTAL_S, DEPARTURE, 25)


@pytest.mark.parametrize("length", [0, -1, float("nan"), float("inf")])
def test_a_route_without_length_is_rejected(length):
    with pytest.raises(ValueError):
        build_checkpoints(meridian_route(100), [], length, TOTAL_S, DEPARTURE, 25)


@pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf")])
def test_a_bad_total_time_is_rejected(seconds):
    with pytest.raises(ValueError):
        build_checkpoints(meridian_route(100), [], TOTAL_M, seconds, DEPARTURE, 25)


@pytest.mark.parametrize("interval", [0, -25, float("nan")])
def test_a_bad_interval_is_rejected(interval):
    with pytest.raises(ValueError):
        build_checkpoints(meridian_route(100), [], TOTAL_M, TOTAL_S, DEPARTURE, interval)


# --------------------------------------------------------------------------------------
# A real TomTom route (first 156.6 miles of a Chicago truck route)
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_route():
    data = json.loads(FIXTURE.read_text())
    return {
        "points": [tuple(p) for p in data["points"]],
        "anchors": [Anchor(i, offset, seconds) for i, offset, seconds in data["anchors"]],
        "total_length_m": data["total_length_m"],
        "total_time_s": data["total_time_s"],
    }


def build_real(real_route, interval, departure=DEPARTURE):
    return build_checkpoints(
        real_route["points"], real_route["anchors"], real_route["total_length_m"],
        real_route["total_time_s"], departure, interval,
    )


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_real_route_invariants(real_route, interval):
    cps = build_real(real_route, interval)
    total_miles = real_route["total_length_m"] / METERS_PER_MILE
    assert cps[0].eta == DEPARTURE
    assert cps[-1].eta == DEPARTURE + timedelta(seconds=real_route["total_time_s"])
    assert sum(cp.represents_miles for cp in cps) == pytest.approx(total_miles, abs=1e-9)
    assert [cp.eta for cp in cps] == sorted(cp.eta for cp in cps)
    assert len(cps) == math.ceil(total_miles / interval) + 1
    assert (cps[0].lat, cps[0].lon) == real_route["points"][0]
    assert (cps[-1].lat, cps[-1].lon) == pytest.approx(real_route["points"][-1])


def test_real_route_checkpoints_lie_on_the_road(real_route):
    # the polyline has a point every ~90 m; every checkpoint must be close to one
    vertices = real_route["points"]
    for cp in build_real(real_route, 10):
        nearest = min(haversine_m(cp.lat, cp.lon, lat, lon) for lat, lon in vertices)
        assert nearest < 500, f"checkpoint at mile {cp.mile} is {nearest:.0f} m from the road"


def test_real_route_etas_match_tomtoms_own_times_between_anchors(real_route):
    # distinct anchors, first one wins where TomTom repeats a point index
    seen, distinct = set(), []
    for anchor in real_route["anchors"]:
        if anchor.point_index not in seen:
            seen.add(anchor.point_index)
            distinct.append(anchor)
    offsets = [a.offset_m for a in distinct]
    times = [a.time_s for a in distinct]

    for cp in build_real(real_route, 5):
        meters = cp.mile * METERS_PER_MILE
        upper = next(i for i, off in enumerate(offsets) if off >= meters - 1e-6)
        if offsets[upper] - meters < 1e-6:
            expected = times[upper]
        else:
            lower = upper - 1
            fraction = (meters - offsets[lower]) / (offsets[upper] - offsets[lower])
            expected = times[lower] + fraction * (times[upper] - times[lower])
        assert seconds_after_departure(cp) == pytest.approx(expected, abs=1)


@pytest.mark.parametrize("anchor_number", [3, 8, 12, 20, 24])
def test_real_route_checkpoint_on_an_anchor_lands_on_the_anchors_point(real_route, anchor_number):
    anchor = real_route["anchors"][anchor_number]
    interval = anchor.offset_m / METERS_PER_MILE  # first checkpoint after the origin is the anchor
    cps = build_real(real_route, interval)
    lat, lon = real_route["points"][anchor.point_index]
    assert cps[1].mile == pytest.approx(interval)
    assert (cps[1].lat, cps[1].lon) == pytest.approx((lat, lon), abs=1e-6)
    assert seconds_after_departure(cps[1]) == pytest.approx(anchor.time_s, abs=1)


def test_real_route_with_the_duplicate_point_index_is_handled(real_route):
    indexes = [a.point_index for a in real_route["anchors"]]
    assert len(indexes) != len(set(indexes)), "fixture should contain a repeated pointIndex"
    build_real(real_route, 10)  # does not raise


# --------------------------------------------------------------------------------------
# Randomised routes: the invariants hold for winding geometry and uneven speeds
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_invariants_on_random_routes(seed):
    rng = random.Random(seed)
    n_points = rng.randint(2, 400)
    lat, lon = rng.uniform(30, 48), rng.uniform(-120, -75)
    points = [(lat, lon)]
    for _ in range(n_points - 1):
        lat += rng.uniform(-0.02, 0.02)
        lon += rng.uniform(-0.02, 0.02)
        points.append((lat, lon))
    length_m = route_length_m(points) * rng.uniform(0.99, 1.01)
    if length_m < 1:
        pytest.skip("degenerate random route")
    total_s = rng.uniform(60, 90_000)

    anchors = []
    if n_points > 2:
        picks = sorted(rng.sample(range(1, n_points - 1), rng.randint(0, min(10, n_points - 2))))
        fractions = sorted(rng.uniform(0, 1) for _ in picks)
        times = sorted(rng.uniform(0, 1) for _ in picks)
        anchors = [Anchor(i, f * length_m, t * total_s) for i, f, t in zip(picks, fractions, times)]
    rng.shuffle(anchors)

    interval = rng.choice([10, 25, 50])
    departure = DEPARTURE + timedelta(minutes=rng.randint(0, 5000))
    cps = build_checkpoints(points, anchors, length_m, total_s, departure, interval)

    total_miles = length_m / METERS_PER_MILE
    assert cps[0].mile == 0 and cps[-1].mile == pytest.approx(total_miles)
    assert sum(cp.represents_miles for cp in cps) == pytest.approx(total_miles, abs=1e-9)
    assert all(a.mile < b.mile for a, b in zip(cps, cps[1:]))
    assert all(a.eta <= b.eta for a, b in zip(cps, cps[1:]))
    assert cps[0].eta == departure.astimezone(UTC)
    assert cps[-1].eta == departure.astimezone(UTC) + timedelta(seconds=round(total_s))
    for cp in cps:
        assert min(p[0] for p in points) - 1e-9 <= cp.lat <= max(p[0] for p in points) + 1e-9
        assert min(p[1] for p in points) - 1e-9 <= cp.lon <= max(p[1] for p in points) + 1e-9
