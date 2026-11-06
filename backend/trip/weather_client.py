"""Fetches checkpoint weather from Open-Meteo, in batches and with a cache (CLAUDE.md section 7).

Measured facts this module is built on (2026-11-06):

* The cost of a request is its number of locations, whatever the time span or variable count.
  A request holds at most 200 locations (400 worked, 700 gave HTTP 414).
* ``start_hour`` / ``end_hour`` give a window anchored at a chosen time; ``forecast_hours`` would
  mean "from now". Everything is asked in UTC.
* Past the end of the forecast Open-Meteo either answers HTTP 400 (``out of allowed range from
  <date> to <date>``) or sends ``null`` for the last hours of the final day.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, NamedTuple, Protocol, Sequence

import requests

from .weather import (
    HOURLY_VARIABLES,
    ForecastOutOfRange,
    HourlySeries,
    WeatherSample,
    WeatherUnavailable,
    nearest_hour,
    parse_range_error,
    parse_response,
    round_location,
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
MAX_LOCATIONS_PER_REQUEST = 200
CACHE_TTL_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
#: Answers worth retrying: rate limit and server trouble.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_WORKERS = 4

_Location = tuple[float, float]
_Key = tuple[_Location, datetime]


class WeatherQuery(NamedTuple):
    """Where and when the weather is wanted: a checkpoint's position and ETA."""

    lat: float
    lon: float
    time: datetime


class _Cache(Protocol):
    def get_many(self, keys: Sequence[str]) -> dict[str, Any]: ...

    def set_many(self, data: dict[str, Any], timeout: int | None = ...) -> Any: ...


def _cache_key(location: _Location, hour: datetime) -> str:
    lat, lon = location
    return f"openmeteo:{lat:.2f}:{lon:.2f}:{hour:%Y%m%dT%H}"


def _format_hour(hour: datetime) -> str:
    return hour.strftime("%Y-%m-%dT%H:%M")


class WeatherClient:
    """Looks up the weather for many (position, ETA) pairs with as few calls as possible."""

    def __init__(
        self,
        session: Any = None,
        cache: _Cache | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if cache is None:
            from django.core.cache import cache as django_cache

            cache = django_cache
        self._session = session if session is not None else requests.Session()
        self._cache = cache
        self._sleep = sleep

    # ----------------------------------------------------------------------------- public

    def get_weather_at(self, queries: Sequence[WeatherQuery]) -> list[WeatherSample]:
        """Weather for each query, in the same order.

        The position is rounded to 2 decimals and the time to the nearest forecast hour. Equal
        (position, hour) pairs are fetched once, and pairs seen within the last hour come from
        the cache. Raises ``ForecastOutOfRange`` or ``WeatherUnavailable``; never fills a
        missing value.
        """
        wanted: list[_Key] = [
            (round_location(q.lat, q.lon), nearest_hour(q.time)) for q in queries
        ]
        unique = list(dict.fromkeys(wanted))
        found = self._read_cache(unique)
        missing = [key for key in unique if key not in found]
        if missing:
            found.update(self._fetch(missing))
        return [found[key] for key in wanted]

    # ------------------------------------------------------------------------------ cache

    def _read_cache(self, keys: Sequence[_Key]) -> dict[_Key, WeatherSample]:
        by_name = {_cache_key(loc, hour): (loc, hour) for loc, hour in keys}
        cached = self._cache.get_many(list(by_name))
        return {by_name[name]: WeatherSample(*values) for name, values in cached.items()}

    def _cache_entries(self, location: _Location, series: HourlySeries) -> dict[str, Any]:
        return {
            _cache_key(location, hour): (s.wind_mph, s.rain_in_hr, s.snow_in_hr)
            for hour, s in series.samples.items()
        }

    # ----------------------------------------------------------------------------- fetch

    def _fetch(self, missing: Sequence[_Key]) -> dict[_Key, WeatherSample]:
        hours_by_location: dict[_Location, set[datetime]] = {}
        for location, hour in missing:
            hours_by_location.setdefault(location, set()).add(hour)

        locations = sorted(hours_by_location)
        batches = [
            locations[i : i + MAX_LOCATIONS_PER_REQUEST]
            for i in range(0, len(locations), MAX_LOCATIONS_PER_REQUEST)
        ]

        def run(batch: list[_Location]) -> dict[_Key, WeatherSample]:
            return self._fetch_batch(batch, {loc: hours_by_location[loc] for loc in batch})

        if len(batches) == 1:
            results = [run(batches[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
                results = list(pool.map(run, batches))

        merged: dict[_Key, WeatherSample] = {}
        for result in results:
            merged.update(result)
        return merged

    def _fetch_batch(
        self, locations: list[_Location], hours: dict[_Location, set[datetime]]
    ) -> dict[_Key, WeatherSample]:
        """One request for up to 200 locations; the window spans every hour they need."""
        every_hour = [hour for needed in hours.values() for hour in needed]
        start, end = min(every_hour), max(every_hour)
        series_list = self._request_series(locations, start, end)

        # Cache first: the good hours stay useful even if another hour turns out to be missing.
        to_cache: dict[str, Any] = {}
        for location, series in zip(locations, series_list):
            to_cache.update(self._cache_entries(location, series))
        self._cache.set_many(to_cache, CACHE_TTL_SECONDS)

        wanted: dict[_Key, WeatherSample] = {}
        for location, series in zip(locations, series_list):
            for hour in hours[location]:
                try:
                    wanted[(location, hour)] = series.sample_at(hour)
                except ForecastOutOfRange as error:
                    if error.forecast_end is None:  # the window held no good hour at all
                        error.forecast_end = self._forecast_end(location, hour.date())
                    raise
        return wanted

    def _request_series(
        self, locations: Sequence[_Location], start: datetime, end: datetime
    ) -> list[HourlySeries]:
        params = {
            "latitude": ",".join(f"{lat:.2f}" for lat, _ in locations),
            "longitude": ",".join(f"{lon:.2f}" for _, lon in locations),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "start_hour": _format_hour(start),
            "end_hour": _format_hour(end),
        }
        status, body = self._get(params)
        if status == 400:
            reason = body.get("reason", "") if isinstance(body, dict) else ""
            last_day = parse_range_error(reason)
            if last_day is None:
                raise WeatherUnavailable(f"Open-Meteo rejected the request: {reason!r}.")
            raise ForecastOutOfRange(
                "The forecast does not reach the time that is needed.",
                forecast_end=self._forecast_end(locations[0], last_day),
            )
        return parse_response(body, len(locations))

    def _forecast_end(self, location: _Location, last_day: date) -> datetime | None:
        """The last hour that has data on ``last_day`` (the 400 error names only the day).

        One extra one-location call, made only while reporting this error. ``None`` if it fails.
        """
        day = datetime(last_day.year, last_day.month, last_day.day, tzinfo=timezone.utc)
        params = {
            "latitude": f"{location[0]:.2f}",
            "longitude": f"{location[1]:.2f}",
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "start_hour": _format_hour(day),
            "end_hour": _format_hour(day + timedelta(hours=23)),
        }
        try:
            status, body = self._get(params)
            if status != 200:
                return None
            return max(parse_response(body, 1)[0].samples, default=None)
        except WeatherUnavailable:
            return None

    def _get(self, params: dict[str, str]) -> tuple[int, Any]:
        """GET with retries for rate limits, server errors and network failures.

        Returns ``(200 or 400, parsed JSON)``; anything else ends as ``WeatherUnavailable``.
        """
        last_problem = "no attempt was made"
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                self._sleep(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))
            try:
                response = self._session.get(
                    OPEN_METEO_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                last_problem = f"{type(exc).__name__}"
                continue
            if response.status_code in _RETRY_STATUSES:
                last_problem = f"HTTP {response.status_code}"
                continue
            if response.status_code not in (200, 400):
                raise WeatherUnavailable(
                    f"Open-Meteo answered with HTTP {response.status_code}."
                )
            try:
                return response.status_code, response.json()
            except ValueError:
                raise WeatherUnavailable(
                    "Open-Meteo answered with something that is not JSON."
                ) from None
        raise WeatherUnavailable(f"Open-Meteo is not responding ({last_problem}).")


_default_client: WeatherClient | None = None


def get_client() -> WeatherClient:
    """The shared client (one HTTP session, the default Django cache)."""
    global _default_client
    if _default_client is None:
        _default_client = WeatherClient()
    return _default_client
