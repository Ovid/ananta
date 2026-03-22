"""Tests for thread-safe rate limiter."""

from __future__ import annotations

import threading
import time

import pytest

from ananta.explorers.arxiv.papers.rate_limit import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_first_call_does_not_wait(self) -> None:
        limiter = RateLimiter(min_interval=1.0)
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1

    def test_second_call_waits_min_interval(self) -> None:
        limiter = RateLimiter(min_interval=0.2)
        limiter.wait()
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.15  # Allow small tolerance

    def test_no_wait_after_interval_elapsed(self) -> None:
        limiter = RateLimiter(min_interval=0.1)
        limiter.wait()
        time.sleep(0.15)
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.05

    def test_backoff_delays_next_call(self) -> None:
        limiter = RateLimiter(min_interval=0.05)
        limiter.wait()
        limiter.backoff(retry_after=0.2)
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.15

    def test_concurrent_threads_are_serialized(self) -> None:
        """Multiple threads calling wait() should be spaced apart."""
        limiter = RateLimiter(min_interval=0.1)
        timestamps: list[float] = []
        lock = threading.Lock()

        def worker() -> None:
            limiter.wait()
            with lock:
                timestamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        timestamps.sort()
        # Each consecutive pair should be at least min_interval apart
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            assert gap >= 0.08, f"Gap {gap:.3f}s between calls {i - 1} and {i} is too small"

    @pytest.mark.parametrize("interval", [0.05, 0.1])
    def test_respects_different_intervals(self, interval: float) -> None:
        limiter = RateLimiter(min_interval=interval)
        limiter.wait()
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        assert elapsed >= interval * 0.9
