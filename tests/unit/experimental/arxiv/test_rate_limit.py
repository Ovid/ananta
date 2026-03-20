"""Tests for rate limiter utility."""

from __future__ import annotations

import time

from ananta.experimental.arxiv.rate_limit import RateLimiter


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_first_call_not_delayed(self) -> None:
        limiter = RateLimiter(min_interval=1.0)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_second_call_delayed(self) -> None:
        limiter = RateLimiter(min_interval=0.2)
        limiter.wait()
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Allow small tolerance

    def test_no_delay_after_interval_elapsed(self) -> None:
        limiter = RateLimiter(min_interval=0.1)
        limiter.wait()
        time.sleep(0.15)  # Wait longer than interval
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    def test_backoff_delays_next_call(self) -> None:
        limiter = RateLimiter(min_interval=0.05)
        limiter.wait()
        limiter.backoff(retry_after=0.2)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Allow small tolerance

    def test_backoff_default_is_5x_interval(self) -> None:
        limiter = RateLimiter(min_interval=0.04)
        limiter.wait()
        limiter.backoff()  # Should default to 0.04 * 5 = 0.2
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15
