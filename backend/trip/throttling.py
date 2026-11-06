"""Request limits per client address.

Every analysis spends free-tier quota that all visitors share: one TomTom routing call and one
Open-Meteo call per checkpoint and per heatmap point (a coast-to-coast trip at 10-mile
checkpoints is about 1,100 of Open-Meteo's 10,000 a day), and every place search is one TomTom
call. Without a limit one client could use it all up in minutes.

The limits are in ``settings.RATE_LIMITS`` and are read on every request, so tests can change
them. The counters live in their own cache: in the weather cache, a long trip's thousands of
entries could push them out.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import caches
from rest_framework.throttling import SimpleRateThrottle


class _ClientThrottle(SimpleRateThrottle):
    scope = ""

    @property
    def cache(self):  # looked up when used, so a test can swap the cache
        return caches["throttle"]

    def get_rate(self) -> str | None:
        return settings.RATE_LIMITS.get(self.scope)

    def get_cache_key(self, request, view) -> str:
        return f"throttle:{self.scope}:{self.get_ident(request)}"


class TripMinuteThrottle(_ClientThrottle):
    scope = "trip_minute"


class TripDayThrottle(_ClientThrottle):
    scope = "trip_day"


class PlacesMinuteThrottle(_ClientThrottle):
    scope = "places_minute"


class PlacesDayThrottle(_ClientThrottle):
    scope = "places_day"


#: ``/api/analyze`` and ``/api/heatmap`` share these: one analysis on screen is one of each.
TRIP_THROTTLES = [TripMinuteThrottle, TripDayThrottle]
#: ``/api/places`` and ``/api/places/reverse``.
PLACES_THROTTLES = [PlacesMinuteThrottle, PlacesDayThrottle]
