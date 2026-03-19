"""Tests for container pool."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from shesha.sandbox.pool import ContainerPool


class TestContainerPool:
    """Tests for ContainerPool."""

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_pool_creates_containers_on_start(self, mock_executor_cls: MagicMock):
        """Pool creates specified number of containers on start."""
        pool = ContainerPool(size=3, image="shesha-sandbox")
        pool.start()

        assert mock_executor_cls.call_count == 3
        assert len(pool._available) == 3

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_acquire_returns_executor(self, mock_executor_cls: MagicMock):
        """Acquiring from pool returns an executor."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()

        executor = pool.acquire()
        assert executor is mock_executor
        assert len(pool._available) == 0

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_release_returns_executor_to_pool(self, mock_executor_cls: MagicMock):
        """Releasing returns executor to pool."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()

        executor = pool.acquire()
        pool.release(executor)
        assert len(pool._available) == 1

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_stop_stops_all_containers(self, mock_executor_cls: MagicMock):
        """Stopping pool stops all containers."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=2, image="shesha-sandbox")
        pool.start()
        pool.stop()

        assert mock_executor.stop.call_count == 2

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_acquire_raises_after_stop(self, mock_executor_cls: MagicMock):
        """Acquiring from a stopped pool raises RuntimeError."""
        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()
        pool.stop()

        with pytest.raises(RuntimeError, match="stopped"):
            pool.acquire()

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_overflow_does_not_block_release(self, mock_executor_cls: MagicMock):
        """Creating overflow container must not hold the pool lock.

        When the pool is exhausted, acquire() creates an overflow container.
        Docker startup takes seconds — the lock must be released during this
        so other threads can release/acquire normally.
        """
        startup_started = threading.Event()
        release_done = threading.Event()

        # Pool executor (returned on start)
        pool_executor = MagicMock()

        # Overflow executor whose start() blocks until we signal
        overflow_executor = MagicMock()

        def slow_start() -> None:
            startup_started.set()
            # Wait for the release to complete — if lock is held, this deadlocks
            assert release_done.wait(timeout=2), "release() was blocked by overflow start()"

        overflow_executor.start.side_effect = slow_start

        call_count = 0

        def make_executor(**kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return pool_executor
            return overflow_executor

        mock_executor_cls.side_effect = make_executor

        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()

        # Drain the pool
        acquired = pool.acquire()

        # Thread 1: acquire when exhausted → triggers overflow
        overflow_result: list[object] = []
        overflow_error: list[Exception] = []

        def acquire_overflow() -> None:
            try:
                overflow_result.append(pool.acquire())
            except Exception as e:
                overflow_error.append(e)

        t1 = threading.Thread(target=acquire_overflow)
        t1.start()

        # Wait for overflow start() to begin
        assert startup_started.wait(timeout=2), "overflow start() never called"

        # Thread 2: release while overflow is starting
        pool.release(acquired)
        release_done.set()

        t1.join(timeout=3)
        assert not overflow_error, f"overflow acquire() raised: {overflow_error}"
        assert len(overflow_result) == 1
        assert overflow_result[0] is overflow_executor

    @patch("shesha.sandbox.pool.ContainerExecutor")
    def test_overflow_container_created_on_pool_exhaustion(self, mock_executor_cls: MagicMock):
        """When pool is exhausted, acquire() creates an overflow container."""
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        pool = ContainerPool(size=1, image="shesha-sandbox")
        pool.start()

        # Drain pool
        pool.acquire()

        # This should create an overflow container
        overflow = pool.acquire()
        assert overflow is mock_executor
        # 1 pool start + 1 overflow = 2 ContainerExecutor constructions
        assert mock_executor_cls.call_count == 2
