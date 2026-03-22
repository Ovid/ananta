"""Rate limiter for external API calls."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Thread-safe rate limiter that enforces a minimum interval and handles 429 backoff."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._last_call: float = 0.0
        self._backoff_until: float = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Block until the minimum interval has elapsed since the last call."""
        with self._lock:
            now = time.monotonic()
            # Respect backoff from 429 responses
            if self._backoff_until > now:
                time.sleep(self._backoff_until - now)
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval and self._last_call > 0:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()

    def backoff(self, retry_after: float | None = None) -> None:
        """Set a backoff period (e.g., after a 429 response).

        Args:
            retry_after: Seconds to wait. Defaults to 5x the min_interval.
        """
        with self._lock:
            delay = retry_after if retry_after is not None else self._min_interval * 5
            self._backoff_until = time.monotonic() + delay
