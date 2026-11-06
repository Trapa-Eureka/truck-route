"""Route line for display: risk-coloured segments and a simplified shape (contract: segments).

A TomTom route has about 10,000 points, far more than a map needs. This module cuts the line
where the risk level changes and simplifies each piece, so the browser draws a few hundred
points per route instead.

* The cuts are at the **end of each checkpoint's stretch** (the midpoints between adjacent
  checkpoints), the same boundaries the miles-per-level numbers use. So the colour of the line
  and the numbers in the route card describe the same stretches.
* Neighbouring stretches with the same level are one segment.
* A cut point is placed on the original line by distance, then simplification keeps the end
  points of every segment, so the segments join up exactly and ``geometry`` is just all the
  segments laid end to end.

Pure: no Django, no network.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Sequence

from .risk import RiskLevel
from .sampling import interpolate

#: Simplification tolerance in degrees of latitude (about 33 m). Smaller than a pixel at the
#: zooms where a whole route is visible, and about 1 pixel at street level.
DEFAULT_TOLERANCE_DEG = 0.0003

LonLat = tuple[float, float]


@dataclass(frozen=True)
class Segment:
    """A piece of route with one risk level; ``coordinates`` are ``(lon, lat)``."""

    level: RiskLevel
    coordinates: tuple[LonLat, ...]


def simplify(coordinates: Sequence[LonLat], tolerance_deg: float) -> list[LonLat]:
    """Douglas-Peucker: drop points closer than ``tolerance_deg`` to the line that remains.

    The first and last point are always kept. Longitude is scaled by ``cos(latitude)`` so the
    tolerance is the same distance in every direction.
    """
    n = len(coordinates)
    if n <= 2:
        return list(coordinates)
    scale = math.cos(math.radians(sum(lat for _, lat in coordinates) / n))
    xy = [(lon * scale, lat) for lon, lat in coordinates]

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = xy[first], xy[last]
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        worst, worst_index = 0.0, -1
        for i in range(first + 1, last):
            x, y = xy[i]
            if length_sq == 0:
                distance = math.hypot(x - x1, y - y1)
            else:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_sq))
                distance = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
            if distance > worst:
                worst, worst_index = distance, i
        if worst_index != -1 and worst > tolerance_deg:
            keep[worst_index] = True
            stack.append((first, worst_index))
            stack.append((worst_index, last))
    return [c for c, kept in zip(coordinates, keep) if kept]


def risk_segments(
    points: Sequence[tuple[float, float]],
    distances_m: Sequence[float],
    stretch_ends_m: Sequence[float],
    levels: Sequence[RiskLevel],
    tolerance_deg: float = DEFAULT_TOLERANCE_DEG,
) -> list[Segment]:
    """Cut a route into risk-coloured segments.

    ``points`` are ``(lat, lon)`` with ``distances_m`` their distance from the origin.
    ``stretch_ends_m[k]`` is where checkpoint ``k``'s stretch ends and ``levels[k]`` its level;
    the last end is the route length. The result runs from the origin to the destination.
    """
    if len(points) != len(distances_m) or len(points) < 2:
        raise ValueError("points and distances_m must match and hold at least 2 points")
    if not levels or len(levels) != len(stretch_ends_m):
        raise ValueError("levels and stretch_ends_m must match and not be empty")
    ends = list(stretch_ends_m)
    if any(b < a for a, b in zip([0.0] + ends, ends)):
        raise ValueError("stretch_ends_m must not decrease")
    ends[-1] = distances_m[-1]  # the last stretch always runs to the destination

    lats = [lat for lat, _ in points]
    lons = [lon for _, lon in points]

    def at(meters: float) -> LonLat:
        return (interpolate(distances_m, lons, meters), interpolate(distances_m, lats, meters))

    # Merge neighbouring stretches that share a level.
    groups: list[tuple[RiskLevel, float, float]] = []
    start = 0.0
    for level, end in zip(levels, ends):
        if groups and groups[-1][0] == level:
            groups[-1] = (level, groups[-1][1], end)
        else:
            groups.append((level, start, end))
        start = end

    segments = []
    for level, begin, finish in groups:
        if finish <= begin:
            continue  # a stretch of no length
        lo = bisect.bisect_right(distances_m, begin)
        hi = bisect.bisect_left(distances_m, finish)
        inner = [(points[i][1], points[i][0]) for i in range(lo, hi)]
        # A cut that lands on a route point, or a repeated point, adds a repeated vertex;
        # simplify() removes it, because a repeat is at distance 0 from the line.
        line = [at(begin), *inner, at(finish)]
        segments.append(Segment(level, tuple(simplify(line, tolerance_deg))))
    return segments


def joined(segments: Sequence[Segment]) -> list[LonLat]:
    """All segments laid end to end (each shared cut point appears once): the display line."""
    line: list[LonLat] = []
    for segment in segments:
        coordinates = segment.coordinates
        if line and coordinates and line[-1] == coordinates[0]:
            coordinates = coordinates[1:]
        line.extend(coordinates)
    return line
