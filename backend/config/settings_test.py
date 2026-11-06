"""Settings used only by the test suite.

``config.settings`` refuses to start without ``DJANGO_SECRET_KEY`` (loaded from the repo-root
``.env`` locally). The tests never need a real secret, so supply a throwaway one when it is
missing. That keeps the tests runnable on a fresh checkout and in CI. It must be set before
``config.settings`` is imported, which is why this lives in a settings module.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production")

from .settings import *  # noqa: E402,F401,F403
