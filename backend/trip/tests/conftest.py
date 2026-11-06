"""Shared test setup."""

import pytest
from django.core.cache import caches


@pytest.fixture(autouse=True)
def fresh_request_counters():
    """Each test starts with no requests counted (trip/throttling.py)."""
    caches["throttle"].clear()
    yield
    caches["throttle"].clear()
