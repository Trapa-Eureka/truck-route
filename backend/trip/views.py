"""HTTP endpoints. They only read the request, call ``analysis`` and return its result."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .analysis import analyze
from .services import get_tomtom, get_weather
from .validation import parse_analyze_request


class AnalyzeView(APIView):
    """``POST /api/analyze``: routes, checkpoints, risk summary and recommendation."""

    def post(self, request) -> Response:
        parsed = parse_analyze_request(request.data, now=timezone.now())
        return Response(analyze(parsed, get_tomtom(), get_weather()))
