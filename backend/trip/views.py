"""HTTP endpoints. They only read the request, call ``analysis`` and return its result."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .analysis import analyze
from .heatmap import heatmap
from .services import get_tomtom, get_weather
from .throttling import PLACES_THROTTLES, TRIP_THROTTLES
from .validation import parse_analyze_request, parse_place_query, parse_position


class AnalyzeView(APIView):
    """``POST /api/analyze``: routes, checkpoints, risk summary and recommendation."""

    throttle_classes = TRIP_THROTTLES

    def post(self, request) -> Response:
        parsed = parse_analyze_request(request.data, now=timezone.now())
        return Response(analyze(parsed, get_tomtom(), get_weather()))


class HeatmapView(APIView):
    """``POST /api/heatmap``: the weather score on a grid around the routes for hours 0 to 48."""

    throttle_classes = TRIP_THROTTLES

    def post(self, request) -> Response:
        parsed = parse_analyze_request(request.data, now=timezone.now())
        return Response(heatmap(parsed, get_tomtom(), get_weather()))


class PlacesView(APIView):
    """``GET /api/places?q=``: up to 5 places, addresses and cities for what is being typed."""

    throttle_classes = PLACES_THROTTLES

    def get(self, request) -> Response:
        suggestions = get_tomtom().suggest(parse_place_query(request.query_params))
        return Response(
            {
                "suggestions": [
                    {
                        "id": item.id,
                        "kind": item.kind,
                        "name": item.name,
                        "detail": item.detail,
                        "label": item.label,
                        "lat": round(item.lat, 5),
                        "lon": round(item.lon, 5),
                    }
                    for item in suggestions
                ]
            }
        )


class ReversePlaceView(APIView):
    """``GET /api/places/reverse?lat=&lon=``: the address at a position ("my location")."""

    throttle_classes = PLACES_THROTTLES

    def get(self, request) -> Response:
        lat, lon = parse_position(request.query_params)
        place = get_tomtom().reverse(lat, lon)
        return Response({"place": {"label": place.label, "lat": place.lat, "lon": place.lon}})
