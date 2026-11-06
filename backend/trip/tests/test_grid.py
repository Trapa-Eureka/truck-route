"""Tests for trip/grid.py: which grid points are near the routes."""

import math
import random

import pytest

from trip.grid import GRID_SPACINGS_DEG, MAX_GRID_POINTS, MILES_PER_DEGREE, corridor_grid, grid_points
from trip.sampling import METERS_PER_MILE, haversine_m
from trip.tests.helpers import recorded_route


def densify(route, step_deg=0.002):
    """Points along a polyline every ``step_deg`` degrees or less (for the brute-force reference)."""
    dense = []
    for (la1, lo1), (la2, lo2) in zip(route, route[1:]):
        n = max(1, math.ceil(max(abs(la2 - la1), abs(lo2 - lo1)) / step_deg))
        dense += [(la1 + (la2 - la1) * k / n, lo1 + (lo2 - lo1) * k / n) for k in range(n)]
    dense.append(route[-1])
    return dense


def miles_to_route(lat, lon, dense):
    return min(haversine_m(lat, lon, la, lo) for la, lo in dense) / METERS_PER_MILE


def reference_check(routes, points, spacing, buffer, slack=0.6, step_deg=0.002):
    """Every returned point is near a route; every node clearly near a route is returned."""
    dense = [d for route in routes for d in densify(route, step_deg)]
    returned = set(points)
    for lat, lon in returned:
        assert miles_to_route(lat, lon, dense) <= buffer + slack, (lat, lon)
    lats = [la for la, _ in dense]
    lons = [lo for _, lo in dense]
    margin = buffer / MILES_PER_DEGREE * 2.5 + spacing
    for i in range(math.floor((min(lats) - margin) / spacing), math.ceil((max(lats) + margin) / spacing) + 1):
        for j in range(math.floor((min(lons) - margin) / spacing), math.ceil((max(lons) + margin) / spacing) + 1):
            node = (i * spacing, j * spacing)
            if miles_to_route(*node, dense) <= buffer - slack:
                assert node in returned, f"missing {node}"


# ------------------------------------------------------------------------------ grid_points


class TestGridPoints:
    def test_a_straight_east_west_route(self):
        route = [(40.0, -90.0), (40.0, -89.0)]
        points = grid_points([route], spacing_deg=0.5, buffer_miles=40)
        lats = {lat for lat, _ in points}
        assert lats == {39.5, 40.0, 40.5}  # 0.5 degree is 34.5 miles, inside 40; 1.0 is 69 miles, outside
        assert min(lon for _, lon in points) == -90.5 and max(lon for _, lon in points) == -88.5

    def test_the_buffer_decides(self):
        route = [(40.0, -90.0), (40.0, -89.0)]
        near = grid_points([route], 0.5, buffer_miles=30)  # 34.5 miles to the next row: out
        assert {lat for lat, _ in near} == {40.0}
        far = grid_points([route], 0.5, buffer_miles=70)
        assert {lat for lat, _ in far} == {39.0, 39.5, 40.0, 40.5, 41.0}  # 1.0 degree is 69.1 miles

    def test_a_node_exactly_on_the_route_with_no_buffer(self):
        assert grid_points([[(40.0, -90.0), (40.0, -89.0)]], 0.5, buffer_miles=0) == [
            (40.0, -90.0), (40.0, -89.5), (40.0, -89.0),
        ]

    def test_points_are_exact_multiples_of_the_spacing(self):
        points = grid_points([[(40.13, -90.37), (41.71, -88.02)]], 0.5, 40)
        assert all(lat % 0.5 == 0 and lon % 0.5 == 0 for lat, lon in points)

    def test_sorted_without_duplicates(self):
        points = grid_points([[(40.0, -90.0), (41.0, -88.0)], [(40.2, -90.0), (41.2, -88.0)]], 0.5, 40)
        assert points == sorted(set(points))

    def test_several_routes_give_the_union(self):
        a = [(40.0, -90.0), (40.0, -89.0)]
        b = [(43.0, -90.0), (43.0, -89.0)]
        assert grid_points([a, b], 0.5, 40) == sorted(set(grid_points([a], 0.5, 40)) | set(grid_points([b], 0.5, 40)))

    def test_two_nearby_routes_share_points(self):
        a = [(40.0, -90.0), (40.0, -89.0)]
        b = [(40.1, -90.0), (40.1, -89.0)]
        both = grid_points([a, b], 0.5, 40)
        assert len(both) == len(set(both)) <= len(grid_points([a], 0.5, 40)) + 6

    def test_no_routes(self):
        assert grid_points([], 0.5, 40) == []
        assert grid_points([[]], 0.5, 40) == []

    def test_a_route_of_one_point(self):
        points = grid_points([[(40.0, -90.0)]], 0.5, 40)
        # the node itself and its four neighbours (34.5 and 26.5 miles away); the diagonals are 43.5
        assert sorted(points) == [(39.5, -90.0), (40.0, -90.5), (40.0, -90.0), (40.0, -89.5), (40.5, -90.0)]
        for lat, lon in points:
            assert haversine_m(40.0, -90.0, lat, lon) / METERS_PER_MILE <= 40.3

    def test_crossing_the_prime_meridian_and_the_equator(self):
        points = grid_points([[(-0.2, -0.7), (0.3, 0.6)]], 0.5, 20)
        assert (0.0, 0.0) in points
        assert all(not (math.copysign(1, lat) < 0 and lat == 0) for lat, _ in points)  # no -0.0

    def test_southern_and_eastern_hemispheres(self):
        reference_check([[(-33.9, 151.0), (-33.0, 152.2)]], grid_points([[(-33.9, 151.0), (-33.0, 152.2)]], 0.5, 40), 0.5, 40)

    def test_never_beyond_the_poles(self):
        points = grid_points([[(89.0, 0.0), (89.9, 10.0)]], 0.5, 100)
        assert all(-90 <= lat <= 90 for lat, _ in points)

    def test_a_long_segment_that_reaches_high_latitudes_keeps_its_wide_margin(self):
        # From the equator to 60 degrees north in one segment: near the north end a degree of
        # longitude is half as long, so nodes a full degree to the side are still within 40 miles.
        route = [(0.0, -90.0), (60.0, -90.0)]
        points = grid_points([route], 0.5, 40)
        assert (60.0, -89.0) in points and (60.0, -91.0) in points
        reference_check([route], points, 0.5, 40, slack=2.0, step_deg=0.05)

    def test_a_north_south_route(self):
        route = [(35.0, -100.0), (36.0, -100.0)]
        points = grid_points([route], 0.5, 40)
        assert {lon for _, lon in points} == {-100.5, -100.0, -99.5}
        assert min(lat for lat, _ in points) == 34.5 and max(lat for lat, _ in points) == 36.5

    def test_the_longitude_margin_widens_away_from_the_equator(self):
        # At 60 degrees north a degree of longitude is half as long: more columns fit in 40 miles.
        equator = grid_points([[(0.0, 0.0), (0.0, 0.0)]], 0.5, 40)
        north = grid_points([[(60.0, 0.0), (60.0, 0.0)]], 0.5, 40)
        assert len({lon for _, lon in north}) > len({lon for _, lon in equator})

    @pytest.mark.parametrize("spacing", [0.5, 1.0, 2.0])
    def test_against_a_brute_force_reference_on_random_routes(self, spacing):
        rng = random.Random(7)
        for _ in range(12):
            lat, lon = rng.uniform(25, 48), rng.uniform(-120, -75)
            route = [(lat, lon)]
            for _ in range(rng.randint(2, 6)):
                lat += rng.uniform(-1.2, 1.2)
                lon += rng.uniform(-1.5, 1.5)
                route.append((lat, lon))
            reference_check([route], grid_points([route], spacing, 40), spacing, 40)

    def test_against_the_reference_with_several_routes(self):
        routes = [[(41.9, -87.6), (41.3, -91.0), (41.6, -95.9)], [(41.9, -87.6), (40.1, -90.0), (39.7, -95.0)]]
        reference_check(routes, grid_points(routes, 0.5, 40), 0.5, 40)

    def test_a_recorded_real_route(self):
        route = list(recorded_route().points)
        points = grid_points([route], 0.5, 40)
        reference_check([route[::4]], points, 0.5, 40, slack=1.5)  # every 4th point is dense enough

    def test_simplifying_the_route_changes_almost_nothing(self):
        route = list(recorded_route().points)
        from trip import grid

        full = set(grid_points([route], 0.5, 40))
        # a much finer tolerance is the same route without the shortcut
        original = grid.SIMPLIFY_TOLERANCE_DEG
        try:
            grid.SIMPLIFY_TOLERANCE_DEG = 0.0
            exact = set(grid_points([route], 0.5, 40))
        finally:
            grid.SIMPLIFY_TOLERANCE_DEG = original
        assert len(full ^ exact) <= 2

    @pytest.mark.parametrize("spacing", [0, -0.5, math.nan, math.inf])
    def test_bad_spacing(self, spacing):
        with pytest.raises(ValueError, match="spacing"):
            grid_points([[(40.0, -90.0)]], spacing, 40)

    @pytest.mark.parametrize("buffer", [-1, math.nan, math.inf])
    def test_bad_buffer(self, buffer):
        with pytest.raises(ValueError, match="buffer"):
            grid_points([[(40.0, -90.0)]], 0.5, buffer)


# ----------------------------------------------------------------------------- corridor_grid


class TestCorridorGrid:
    def test_a_small_trip_gets_the_finest_grid(self):
        points, spacing = corridor_grid([[(41.9, -87.6), (43.1, -89.3)]])
        assert spacing == 0.5 and 0 < len(points) <= MAX_GRID_POINTS

    def test_it_matches_grid_points_at_its_spacing(self):
        route = [(41.9, -87.6), (43.1, -89.3)]
        points, spacing = corridor_grid([route])
        assert points == grid_points([route], spacing, 40)

    def test_a_big_trip_gets_a_coarser_grid(self):
        # three routes across the whole country, far apart: too many points at 0.5 degrees
        routes = [
            [(47.6, -122.3), (45.0, -93.0), (42.4, -71.0)],
            [(37.8, -122.4), (38.0, -95.0), (37.0, -77.0)],
            [(32.7, -117.1), (32.0, -97.0), (30.3, -81.7)],
        ]
        assert len(grid_points(routes, 0.5, 40)) > MAX_GRID_POINTS
        points, spacing = corridor_grid(routes)
        assert spacing > 0.5 and len(points) <= MAX_GRID_POINTS

    def test_exactly_the_limit_is_allowed(self):
        route = [(41.9, -87.6), (39.7, -105.0)]
        count = len(grid_points([route], 0.5, 40))
        assert corridor_grid([route], max_points=count)[1] == 0.5
        assert corridor_grid([route], max_points=count - 1)[1] > 0.5

    def test_a_lower_limit_means_a_coarser_grid(self):
        route = [(41.9, -87.6), (39.7, -105.0)]
        _, fine = corridor_grid([route], max_points=10_000)
        _, coarse = corridor_grid([route], max_points=60)
        assert fine == 0.5 and coarse > fine

    def test_the_coarsest_grid_is_returned_even_if_over_the_limit(self):
        route = [(47.6, -122.3), (25.8, -80.2)]
        points, spacing = corridor_grid([route], max_points=1)
        assert spacing == GRID_SPACINGS_DEG[-1] and len(points) > 1

    def test_spacings_get_coarser(self):
        assert list(GRID_SPACINGS_DEG) == sorted(GRID_SPACINGS_DEG) and GRID_SPACINGS_DEG[0] == 0.5


class TestLongSegmentsAreCutIntoPieces:
    def test_a_long_straight_route_over_many_degrees_of_longitude(self):
        route = [(35.0, -120.0), (50.0, -75.0)]  # one segment across the country
        reference_check([route], grid_points([route], 0.5, 40), 0.5, 40, slack=2.0, step_deg=0.05)

    def test_the_result_does_not_depend_on_where_the_route_is_cut(self):
        whole = [(40.0, -100.0), (46.0, -90.0)]
        cut = [(40.0, -100.0), (43.0, -95.0), (46.0, -90.0)]  # the same straight line with a middle point
        assert set(grid_points([whole], 0.5, 40)) ^ set(grid_points([cut], 0.5, 40)) == set()
