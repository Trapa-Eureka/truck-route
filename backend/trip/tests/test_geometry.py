"""Tests for trip/geometry.py: simplification and risk-coloured segments."""

import math

import pytest

from trip.geometry import Segment, joined, risk_segments, simplify
from trip.risk import RiskLevel
from trip.sampling import haversine_m

L, M, H, S, N = (RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)


def line(n, step=0.01, lat=40.0):
    """n points going east along a parallel, as (lat, lon) plus cumulative metres."""
    points = [(lat, -90.0 + i * step) for i in range(n)]
    distances = [0.0]
    for a, b in zip(points, points[1:]):
        distances.append(distances[-1] + haversine_m(*a, *b))
    return points, distances


# ------------------------------------------------------------------------------ simplify


class TestSimplify:
    def test_a_straight_line_keeps_only_its_ends(self):
        coords = [(-90.0 + i * 0.01, 40.0) for i in range(100)]
        assert simplify(coords, 0.0003) == [coords[0], coords[-1]]

    def test_a_corner_is_kept(self):
        coords = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (1.0, 0.5), (1.0, 1.0)]
        assert simplify(coords, 0.01) == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]

    def test_a_small_wiggle_below_the_tolerance_goes(self):
        coords = [(0.0, 0.0), (0.5, 0.0001), (1.0, 0.0)]
        assert simplify(coords, 0.001) == [(0.0, 0.0), (1.0, 0.0)]

    def test_a_wiggle_above_the_tolerance_stays(self):
        coords = [(0.0, 0.0), (0.5, 0.01), (1.0, 0.0)]
        assert simplify(coords, 0.001) == coords

    def test_ends_are_always_kept(self):
        coords = [(0.0, 0.0), (0.2, 0.3), (0.4, 0.0), (0.6, 0.3), (0.8, 0.0)]
        out = simplify(coords, 10.0)
        assert out[0] == coords[0] and out[-1] == coords[-1]

    @pytest.mark.parametrize("n", [0, 1, 2])
    def test_short_lines_are_unchanged(self, n):
        coords = [(0.0, 0.0), (1.0, 1.0)][:n]
        assert simplify(coords, 0.1) == coords

    def test_a_closed_loop_does_not_collapse(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
        assert len(simplify(coords, 0.01)) >= 4

    def test_result_is_a_subsequence_in_order(self):
        coords = [(i * 0.01, math.sin(i / 7) * 0.05) for i in range(300)]
        out = simplify(coords, 0.002)
        positions = [coords.index(c) for c in out]
        assert positions == sorted(positions) and len(out) < len(coords)

    def test_no_dropped_point_is_farther_than_the_tolerance(self):
        coords = [(i * 0.01, math.sin(i / 7) * 0.05) for i in range(300)]
        tolerance = 0.002
        out = simplify(coords, tolerance)
        kept = [coords.index(c) for c in out]
        for a, b in zip(kept, kept[1:]):
            (x1, y1), (x2, y2) = coords[a], coords[b]
            for i in range(a + 1, b):
                x, y = coords[i]
                length_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
                t = max(0, min(1, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / length_sq))
                assert math.hypot(x - (x1 + t * (x2 - x1)), y - (y1 + t * (y2 - y1))) <= tolerance * 1.01

    def test_longitude_is_scaled_by_latitude(self):
        # Going north at 60 degrees: 0.0004 degrees of longitude is only 0.0002 degrees of
        # real distance, under the 0.0003 tolerance, so the wiggle must be dropped.
        coords = [(-90.0, 60.0), (-90.0 + 0.0004, 60.5), (-90.0, 61.0)]
        assert simplify(coords, 0.0003) == [coords[0], coords[-1]]
        # the same wiggle in latitude is a full 0.0004 and stays
        assert len(simplify([(0.0, 60.0), (0.5, 60.0004), (1.0, 60.0)], 0.0003)) == 3

    def test_a_spike_beyond_the_end_of_the_chord_is_kept(self):
        # The middle point lies far past the end of the chord, almost on its line. The distance
        # to the chord *segment* is large, so it must stay.
        coords = [(0.0, 0.0), (5.0, 0.0001), (1.0, 0.0)]
        assert simplify(coords, 0.001) == coords

    def test_a_point_exactly_at_the_tolerance_is_dropped(self):
        coords = [(0.0, 0.0), (0.5, 0.5), (1.0, 0.0)]
        assert simplify(coords, 0.5) == [(0.0, 0.0), (1.0, 0.0)]

    def test_identical_end_points_with_points_between(self):
        coords = [(0.0, 0.0), (0.5, 0.5), (0.0, 0.0)]
        assert (0.5, 0.5) in simplify(coords, 0.01)


# ---------------------------------------------------------------------------- risk_segments


class TestRiskSegments:
    def setup_method(self):
        self.points, self.distances = line(101)
        self.total = self.distances[-1]

    def ends(self, *fractions):
        return [f * self.total for f in fractions]

    def test_one_level_is_one_segment_from_origin_to_destination(self):
        [seg] = risk_segments(self.points, self.distances, self.ends(0.5, 1.0), [L, L])
        assert seg.level == L
        assert seg.coordinates[0] == (-90.0, 40.0)
        assert seg.coordinates[-1] == pytest.approx((-89.0, 40.0))

    def test_cuts_are_where_the_level_changes(self):
        segs = risk_segments(self.points, self.distances, self.ends(0.25, 0.5, 0.75, 1.0), [L, L, S, L])
        assert [s.level for s in segs] == [L, S, L]
        # the Severe stretch runs from 50% to 75% of the route (lon -89.5 to -89.25)
        assert segs[1].coordinates[0][0] == pytest.approx(-89.5)
        assert segs[1].coordinates[-1][0] == pytest.approx(-89.25)

    def test_neighbouring_stretches_with_the_same_level_merge(self):
        segs = risk_segments(self.points, self.distances, self.ends(0.2, 0.4, 0.6, 0.8, 1.0), [M, M, H, H, H])
        assert [s.level for s in segs] == [M, H]
        assert segs[0].coordinates[-1][0] == pytest.approx(-89.6)

    def test_the_same_level_apart_stays_two_segments(self):
        segs = risk_segments(self.points, self.distances, self.ends(0.3, 0.6, 1.0), [S, L, S])
        assert [s.level for s in segs] == [S, L, S]

    def test_segments_join_exactly(self):
        segs = risk_segments(self.points, self.distances, self.ends(0.1, 0.35, 0.7, 1.0), [L, H, S, L])
        for a, b in zip(segs, segs[1:]):
            assert a.coordinates[-1] == b.coordinates[0]

    def test_the_last_stretch_always_reaches_the_destination(self):
        # an end a little short of the route length (float noise) must still reach the end exactly
        segs = risk_segments(self.points, self.distances, [self.total * 0.5, self.total * 0.999999], [L, S])
        assert segs[-1].coordinates[-1] == (self.points[-1][1], self.points[-1][0])

    def test_a_stretch_of_no_length_makes_no_segment(self):
        half = self.total * 0.5
        segs = risk_segments(self.points, self.distances, [half, half, self.total], [L, H, L])
        assert [s.level for s in segs] == [L, L]
        assert all(len(set(s.coordinates)) >= 2 for s in segs)

    def test_a_repeated_route_point_does_not_make_a_repeated_vertex(self):
        # a zig-zag with its corner listed twice: the corner must appear once
        points = [(40.0, -90.0), (40.1, -89.9), (40.1, -89.9), (40.0, -89.8)]
        distances = [0.0]
        for a, b in zip(points, points[1:]):
            distances.append(distances[-1] + haversine_m(*a, *b))
        [seg] = risk_segments(points, distances, [distances[-1]], [L])
        assert all(a != b for a, b in zip(seg.coordinates, seg.coordinates[1:]))
        assert len(seg.coordinates) == 3

    def test_every_vertex_is_on_the_original_line(self):
        points, distances = line(500, step=0.002)
        for seg in risk_segments(points, distances, [distances[-1] * f for f in (0.4, 1.0)], [L, H]):
            for lon, lat in seg.coordinates:
                assert lat == pytest.approx(40.0)

    def test_simplification_reduces_the_points(self):
        points, distances = line(2000, step=0.0005)
        [seg] = risk_segments(points, distances, [distances[-1]], [L])
        assert len(seg.coordinates) == 2  # a straight line

    def test_a_curve_keeps_its_shape(self):
        points = [(40.0 + 0.2 * math.sin(i / 30), -90.0 + i * 0.002) for i in range(1000)]
        distances = [0.0]
        for a, b in zip(points, points[1:]):
            distances.append(distances[-1] + haversine_m(*a, *b))
        [seg] = risk_segments(points, distances, [distances[-1]], [L], tolerance_deg=0.0003)
        assert 20 < len(seg.coordinates) < 400

    def test_a_cut_inside_a_long_gap_between_points_is_interpolated(self):
        points = [(40.0, -90.0), (40.0, -89.0)]
        distances = [0.0, haversine_m(40.0, -90.0, 40.0, -89.0)]
        segs = risk_segments(points, distances, [distances[1] * 0.25, distances[1]], [L, H])
        assert segs[0].coordinates[-1][0] == pytest.approx(-89.75)

    def test_a_cut_exactly_on_a_route_point_is_not_duplicated(self):
        segs = risk_segments(self.points, self.distances, [self.distances[50], self.total], [L, H])
        assert segs[0].coordinates[-1] == segs[1].coordinates[0]
        assert len(set(segs[0].coordinates)) == len(segs[0].coordinates)

    def test_a_single_stretch(self):
        segs = risk_segments(self.points, self.distances, [self.total], [N])
        assert [s.level for s in segs] == [N]

    # -- validation

    def test_mismatched_points_and_distances(self):
        with pytest.raises(ValueError):
            risk_segments(self.points, self.distances[:-1], [self.total], [L])

    def test_too_few_points(self):
        with pytest.raises(ValueError):
            risk_segments([(40.0, -90.0)], [0.0], [0.0], [L])

    def test_mismatched_levels_and_ends(self):
        with pytest.raises(ValueError):
            risk_segments(self.points, self.distances, [self.total], [L, H])

    def test_no_levels(self):
        with pytest.raises(ValueError):
            risk_segments(self.points, self.distances, [], [])

    def test_decreasing_ends(self):
        with pytest.raises(ValueError, match="decrease"):
            risk_segments(self.points, self.distances, [self.total * 0.6, self.total * 0.3, self.total], [L, H, L])


# ----------------------------------------------------------------------------------- joined


class TestJoined:
    def test_shared_cut_points_appear_once(self):
        a = Segment(L, ((0.0, 0.0), (1.0, 0.0)))
        b = Segment(H, ((1.0, 0.0), (2.0, 0.0)))
        assert joined([a, b]) == [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]

    def test_empty(self):
        assert joined([]) == []

    def test_joined_equals_the_union_of_the_segments(self):
        points, distances = line(300, step=0.003)
        ends = [distances[-1] * f for f in (0.3, 0.6, 1.0)]
        segs = risk_segments(points, distances, ends, [L, S, L])
        line_ = joined(segs)
        assert line_[0] == segs[0].coordinates[0] and line_[-1] == segs[-1].coordinates[-1]
        assert len(line_) == sum(len(s.coordinates) for s in segs) - (len(segs) - 1)
