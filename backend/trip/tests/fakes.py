"""Small stand-ins for HTTP and the cache, shared by the client tests."""

from __future__ import annotations


class FakeResponse:
    def __init__(self, status_code=200, body=None, not_json=False):
        self.status_code = status_code
        self._body = body
        self._not_json = not_json

    def json(self):
        if self._not_json:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """``get(url, params, timeout)`` answers with ``handler(url, params)``; an exception is raised."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []  # (url, params)
        self.timeouts = []

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params)))
        self.timeouts.append(timeout)
        result = self.handler(url, params)
        if isinstance(result, Exception):
            raise result
        return result


class DictCache:
    """Minimal Django-cache look-alike (get / set / get_many / set_many)."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, timeout=None):
        self.data[key] = value

    def get_many(self, keys):
        return {k: self.data[k] for k in keys if k in self.data}

    def set_many(self, data, timeout=None):
        self.data.update(data)
