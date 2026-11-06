"""GET with retries, shared by the TomTom and Open-Meteo clients."""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
#: Answers worth retrying: rate limit and server trouble.
RETRY_STATUSES = {429, 500, 502, 503, 504}
#: Answers handed back to the caller: success, and "bad request" whose body says why.
PASS_STATUSES = (200, 400)


def get_json(
    session: Any,
    url: str,
    params: dict[str, Any],
    *,
    service: str,
    error: type[Exception],
    timeout: float,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, Any]:
    """GET ``url`` and return ``(status, parsed JSON)`` for a 200 or 400 answer.

    Rate limits (429), server errors (5xx) and network failures are retried up to
    ``MAX_ATTEMPTS`` times with a pause that doubles. Everything else, and running out of
    attempts, raises ``error`` with a message that names ``service``. Messages never contain
    the URL, because it carries API keys.
    """
    last_problem = "no attempt was made"
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            sleep(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))
        try:
            response = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_problem = type(exc).__name__
            continue
        if response.status_code in RETRY_STATUSES:
            last_problem = f"HTTP {response.status_code}"
            continue
        if response.status_code not in PASS_STATUSES:
            raise error(f"{service} answered with HTTP {response.status_code}.")
        try:
            return response.status_code, response.json()
        except ValueError:
            raise error(f"{service} answered with something that is not JSON.") from None
    raise error(f"{service} is not responding ({last_problem}).")
