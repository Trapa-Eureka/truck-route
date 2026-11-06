"""The heatmap grid: weather points on a lat/lon grid around the routes (CLAUDE.md section 7).

A point is on the grid when it is within ``buffer_miles`` of any of the routes. Points sit on
exact multiples of the spacing (0.5 degrees is about 34 miles), so the same place always gives
the same point and the weather cache is shared between trips.

Pure: no Django, no network.
"""

from __future__ import annotations

import math
from typing import Sequence

from .geometry import simplify
from .sampling import EARTH_RADIUS_M, METERS_PER_MILE

MILES_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180 / METERS_PER_MILE

#: Spacing in degrees: 0.5 is about 34 miles. The coarser ones are used only for very large trips.
GRID_SPACINGS_DEG = (0.5, 1.0, 2.0)
#: One request holds at most 200 locations and every point costs one weather call, so a trip that
#: needs more points than this gets a coarser grid.
MAX_GRID_POINTS = 600
#: Routes are simplified to about 1 km before the distance test (a route has about 10,000 points).
SIMPLIFY_TOLERANCE_DEG = 0.01

#: A segment longer than this is cut into pieces before the distance test. The test treats the
#: map around a segment as flat, which is only accurate when the segment is short: a straight line
#: over many degrees of latitude would measure a wide margin at its far end with the wrong scale.
MAX_PIECE_DEG = 0.25

# (lat, lon)
Point = tuple[float, float]


def _pieces(a: Point, b: Point) -> list[tuple[Point, Point]]:
    """The segment a-b cut into pieces of at most ``MAX_PIECE_DEG`` in latitude and longitude."""
    count = max(1, math.ceil(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / MAX_PIECE_DEG))
    nodes = [(a[0] + (b[0] - a[0]) * k / count, a[1] + (b[1] - a[1]) * k / count) for k in range(count + 1)]
    return list(zip(nodes, nodes[1:]))


def _distance_to_segment_miles(lat: float, lon: float, a: Point, b: Point) -> float:
    """Miles from (lat, lon) to the segment a-b, on a flat map local to the segment."""
    scale = math.cos(math.radians((a[0] + b[0] + lat) / 3))
    ax, ay = (a[1] - lon) * scale, a[0] - lat
    dx, dy = (b[1] - a[1]) * scale, b[0] - a[0]
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.hypot(ax + t * dx, ay + t * dy) * MILES_PER_DEGREE


def grid_points(
    routes: Sequence[Sequence[Point]],
    spacing_deg: float = 0.5,
    buffer_miles: float = 40.0,
) -> list[Point]:
    """Grid points within ``buffer_miles`` of any route, sorted by (lat, lon).

    ``routes`` are lists of ``(lat, lon)``. Each point is returned once, however many routes
    pass near it.
    """
    if not spacing_deg > 0 or not math.isfinite(spacing_deg):
        raise ValueError(f"spacing_deg must be positive, got {spacing_deg!r}")
    if not buffer_miles >= 0 or not math.isfinite(buffer_miles):
        raise ValueError(f"buffer_miles must not be negative, got {buffer_miles!r}")

    found: set[Point] = set()
    lat_margin = buffer_miles / MILES_PER_DEGREE
    for route in routes:
        if len(route) == 0:
            continue
        line = [(lat, lon) for lon, lat in simplify([(lon, lat) for lat, lon in route], SIMPLIFY_TOLERANCE_DEG)]
        segments = (
            [piece for a, b in zip(line, line[1:]) for piece in _pieces(a, b)]
            if len(line) > 1
            else [(line[0], line[0])]
        )
        for a, b in segments:
            lat_lo, lat_hi = min(a[0], b[0]) - lat_margin, max(a[0], b[0]) + lat_margin
            # Degrees of longitude are shorter away from the equator: use the widest case.
            widest = math.cos(math.radians(min(89.0, max(abs(lat_lo), abs(lat_hi)))))
            lon_margin = lat_margin / widest
            lon_lo, lon_hi = min(a[1], b[1]) - lon_margin, max(a[1], b[1]) + lon_margin
            for i in range(math.ceil(lat_lo / spacing_deg), math.floor(lat_hi / spacing_deg) + 1):
                lat = i * spacing_deg
                if not -90 <= lat <= 90:
                    continue
                for j in range(math.ceil(lon_lo / spacing_deg), math.floor(lon_hi / spacing_deg) + 1):
                    lon = j * spacing_deg
                    if (lat, lon) not in found and _distance_to_segment_miles(lat, lon, a, b) <= buffer_miles:
                        found.add((lat, lon))
    return sorted(found)


def corridor_grid(
    routes: Sequence[Sequence[Point]],
    buffer_miles: float = 40.0,
    max_points: int = MAX_GRID_POINTS,
) -> tuple[list[Point], float]:
    """The grid for a trip: the finest spacing that stays within ``max_points``.

    Returns ``(points, spacing_deg)``. If even the coarsest spacing is over the limit, that
    grid is returned anyway (it is bounded by the size of the country).
    """
    for spacing in GRID_SPACINGS_DEG:
        points = grid_points(routes, spacing, buffer_miles)
        if len(points) <= max_points:
            return points, spacing
    return points, GRID_SPACINGS_DEG[-1]
