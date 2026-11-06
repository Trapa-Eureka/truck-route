"""Weather at a checkpoint's ETA: types, hour matching and Open-Meteo response parsing.

Everything here is pure: no Django, no network, no clock (CLAUDE.md sections 2, 7 and 8).
``weather_client.py`` does the HTTP calls and the caching and uses this module to read the
answers.

Rules that matter for correctness
---------------------------------
* The weather for a checkpoint is the forecast for the **hour nearest to its ETA** (a time
  exactly on the half hour goes to the later hour). The heatmap slider shows whole forecast
  hours too, so a checkpoint and the heatmap agree on which forecast they show.
* A missing value is never turned into 0. A ``null`` hour past the end of the forecast is
  ``ForecastOutOfRange``; anything else that is missing or malformed is ``WeatherUnavailable``.
  A stretch with unknown weather must not look safe.
* Units are requested from Open-Meteo already in mph and inches, and the response labels are
  checked, so a silent unit change cannot slip through.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

#: Hourly variables requested from Open-Meteo.
HOURLY_VARIABLES = ("wind_speed_10m", "rain", "showers", "snowfall")

#: Unit labels the response must carry. Open-Meteo writes miles per hour as ``mp/h`` (measured
#: 2026-11-06); ``mph`` is accepted too in case the label is ever corrected.
_ACCEPTED_UNITS = {
    "wind_speed_10m": {"mp/h", "mph"},
    "rain": {"inch"},
    "showers": {"inch"},
    "snowfall": {"inch"},
}

# ``rain + showers`` is a sum of two decimals (0.09 + 0.01 is 0.09999999999999999 in floating
# point), which would fall just under the 0.10 in/hr boundary. Open-Meteo gives 3 decimals.
_RAIN_DECIMALS = 4

_RANGE_ERROR = re.compile(
    r"out of allowed range from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})"
)


@dataclass(frozen=True)
class WeatherSample:
    """Weather at one place and hour, in the units of the risk tables."""

    wind_mph: float
    #: ``rain + showers`` of the preceding hour, in inches (= inches per hour).
    rain_in_hr: float
    #: ``snowfall`` of the preceding hour, in inches of snow (= inches per hour).
    snow_in_hr: float


class WeatherError(Exception):
    """Base class: the weather for a checkpoint could not be determined."""


class WeatherUnavailable(WeatherError):
    """Open-Meteo failed, timed out, or answered with data we cannot trust (HTTP 502)."""


class ForecastOutOfRange(WeatherError):
    """A needed hour lies past the end of the forecast (HTTP 422)."""

    def __init__(self, message: str, forecast_end: datetime | None = None) -> None:
        super().__init__(message)
        #: Last hour (UTC) that still has a forecast, when known.
        self.forecast_end = forecast_end


def round_location(lat: float, lon: float) -> tuple[float, float]:
    """Round a coordinate to 2 decimals (about 1 km), the resolution weather is fetched at.

    Nearby checkpoints then share one cache entry. ``-0.0`` is normalised to ``0.0``.
    """
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(f"coordinate is not finite: {(lat, lon)!r}")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"coordinate is out of range: {(lat, lon)!r}")
    return round(lat, 2) + 0.0, round(lon, 2) + 0.0


def nearest_hour(moment: datetime) -> datetime:
    """The forecast hour (UTC, on the hour) nearest to ``moment``; :30 rounds up."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("time must be timezone-aware")
    utc = moment.astimezone(timezone.utc)
    floor = utc.replace(minute=0, second=0, microsecond=0)
    if utc - floor >= timedelta(minutes=30):
        return floor + timedelta(hours=1)
    return floor


@dataclass(frozen=True)
class HourlySeries:
    """The usable hours of one location's answer, plus the hours that came back ``null``."""

    samples: dict[datetime, WeatherSample]
    null_hours: frozenset[datetime]

    def sample_at(self, hour: datetime) -> WeatherSample:
        """The sample for ``hour``, or the error that explains why there is none.

        A ``null`` hour *after* the last good hour is the end of the forecast. A ``null`` in
        the middle, or an hour the answer does not contain at all, means the data is broken.
        """
        sample = self.samples.get(hour)
        if sample is not None:
            return sample
        last_good = max(self.samples, default=None)
        if hour in self.null_hours and (last_good is None or hour > last_good):
            raise ForecastOutOfRange(
                f"No forecast for {hour.isoformat()}.", forecast_end=last_good
            )
        raise WeatherUnavailable(f"The weather data has no value for {hour.isoformat()}.")


def _number(value: object, name: str) -> float | None:
    """``None`` for ``null``; otherwise a finite, non-negative float."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherUnavailable(f"The weather data has a non-numeric {name}: {value!r}.")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise WeatherUnavailable(f"The weather data has an invalid {name}: {value!r}.")
    return number


def _parse_time(text: object) -> datetime:
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        raise WeatherUnavailable(f"The weather data has an invalid time: {text!r}.") from None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)  # requested with timezone=UTC
    return moment.astimezone(timezone.utc)


def _check_units(units: object) -> None:
    if not isinstance(units, dict):
        raise WeatherUnavailable("The weather data does not state its units.")
    for name, accepted in _ACCEPTED_UNITS.items():
        if units.get(name) not in accepted:
            raise WeatherUnavailable(
                f"The weather data has unexpected units for {name}: {units.get(name)!r}."
            )


def _parse_entry(entry: object) -> HourlySeries:
    if not isinstance(entry, dict) or not isinstance(entry.get("hourly"), dict):
        raise WeatherUnavailable("The weather data is not in the expected format.")
    _check_units(entry.get("hourly_units"))

    hourly = entry["hourly"]
    times = hourly.get("time")
    columns = [hourly.get(name) for name in HOURLY_VARIABLES]
    if not isinstance(times, list) or not all(isinstance(c, list) for c in columns):
        raise WeatherUnavailable("The weather data is missing a variable.")
    if any(len(c) != len(times) for c in columns):
        raise WeatherUnavailable("The weather data has columns of different lengths.")

    samples: dict[datetime, WeatherSample] = {}
    null_hours: set[datetime] = set()
    for i, text in enumerate(times):
        hour = _parse_time(text)
        wind, rain, showers, snow = (
            _number(column[i], name) for column, name in zip(columns, HOURLY_VARIABLES)
        )
        if wind is None or rain is None or showers is None or snow is None:
            null_hours.add(hour)
            continue
        samples[hour] = WeatherSample(
            wind_mph=wind,
            rain_in_hr=round(rain + showers, _RAIN_DECIMALS),
            snow_in_hr=snow,
        )
    return HourlySeries(samples=samples, null_hours=frozenset(null_hours))


def parse_response(payload: Any, location_count: int) -> list[HourlySeries]:
    """Read an Open-Meteo answer for ``location_count`` locations, in request order.

    Open-Meteo answers with one object for a single location and a list for several.
    """
    if isinstance(payload, dict) and payload.get("error"):
        raise WeatherUnavailable(f"Open-Meteo reported an error: {payload.get('reason')!r}.")
    entries = payload if isinstance(payload, list) else [payload]
    if len(entries) != location_count:
        raise WeatherUnavailable(
            f"Open-Meteo returned {len(entries)} locations, expected {location_count}."
        )
    return [_parse_entry(entry) for entry in entries]


def parse_range_error(reason: object) -> date | None:
    """The last forecast day named by an "out of allowed range" error, else ``None``.

    Example reason: ``Parameter 'start_hour' is out of allowed range from 2026-08-05 to
    2026-11-21``. Any other error text returns ``None``.
    """
    match = _RANGE_ERROR.search(str(reason))
    if match is None:
        return None
    return date.fromisoformat(match.group(2))
