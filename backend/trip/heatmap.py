"""The heatmap use case: a risk score at every grid point for each of the next 48 hours.

Slider hour ``h`` is the forecast ``h`` hours after the departure hour. The departure hour is the
departure rounded to the nearest hour (CLAUDE.md sections 2 and 7). At a whole hour the wind is
the value at that hour and rain and snow are the sums of the hour before it; a checkpoint, whose
ETA is rarely on the hour, reads wind at the nearest hour and rain and snow at the hour that
contains its ETA (``weather.py``).

Each point gets a **score** from 0 to 4 (``risk.risk_score``): the weather's strength, continuous,
so the map can show 5 mph wind and 20 mph wind as different even though both are "Low". The whole
part of the score is the risk level by the same rules as checkpoints, load rules included, so the
route and the heatmap use one scale and one set of colors. All 49 hours come back in one response:
moving the slider in the browser never calls the API again.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .analysis import RoutingService, WeatherService, resolve_trip
from .grid import corridor_grid
from .risk import assess_checkpoint, risk_score
from .validation import AnalyzeRequest
from .weather import nearest_hour
from .weather_client import WeatherQuery

#: Slider hours 0 to 48.
HOURS = 49


def heatmap(
    request: AnalyzeRequest, routing: RoutingService, weather: WeatherService
) -> dict[str, Any]:
    """Build the ``POST /api/heatmap`` response body.

    Raises the domain exceptions that ``errors.api_exception_handler`` turns into API errors.
    A missing forecast value is never turned into a level: it is ``ForecastOutOfRange`` or
    ``WeatherUnavailable``.
    """
    _, _, raw_routes = resolve_trip(request, routing)

    points, spacing = corridor_grid([raw.points for raw in raw_routes])
    start = nearest_hour(request.departure)

    # Every point at every hour, in one call: equal places are fetched once and batched.
    queries = [
        WeatherQuery(lat, lon, start + timedelta(hours=hour))
        for lat, lon in points
        for hour in range(HOURS)
    ]
    samples = weather.get_weather_at(queries)

    scores = [[0.0] * len(points) for _ in range(HOURS)]
    for position, sample in enumerate(samples):
        point, hour = divmod(position, HOURS)
        risk = assess_checkpoint(
            sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, request.load_weight_lb
        )
        score = risk_score(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, risk.level)
        # 2 decimals are plenty for a picture. Rounding cannot change the level: a score is at most
        # (level + 0.99) and at least the level itself.
        scores[hour][point] = round(score, 2)

    return {
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hours": HOURS,
        "spacing_deg": spacing,
        "points": [[lon, lat] for lat, lon in points],
        "scores": scores,
    }
