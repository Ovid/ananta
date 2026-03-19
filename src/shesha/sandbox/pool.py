"""Container pool for managing warm sandbox containers."""

import logging
import threading
from collections import deque

from shesha.sandbox.base import SandboxExecutor
from shesha.sandbox.executor import ContainerExecutor

logger = logging.getLogger(__name__)


class ContainerPool:
    """Pool of pre-warmed containers for fast execution."""

    def __init__(
        self,
        size: int = 3,
        image: str = "shesha-sandbox",
        memory_limit: str = "512m",
    ) -> None:
        """Initialize pool settings."""
        self.size = size
        self.image = image
        self.memory_limit = memory_limit
        self._available: deque[SandboxExecutor] = deque()
        self._in_use: set[SandboxExecutor] = set()
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        """Start the pool and warm up containers."""
        if self._started:
            return
        logger.info("Starting container pool (size=%d, image=%s)", self.size, self.image)
        for _ in range(self.size):
            executor = ContainerExecutor(
                image=self.image,
                memory_limit=self.memory_limit,
            )
            executor.start()
            self._available.append(executor)
        self._started = True
        logger.info("Container pool started with %d warm containers", self.size)

    def stop(self) -> None:
        """Stop all containers in the pool."""
        logger.info("Stopping container pool")
        with self._lock:
            for executor in self._available:
                executor.stop()
            for executor in self._in_use:
                executor.stop()
            self._available.clear()
            self._in_use.clear()
            self._started = False

    def acquire(self) -> SandboxExecutor:
        """Acquire an executor from the pool."""
        with self._lock:
            if not self._started:
                raise RuntimeError("Cannot acquire from a stopped pool")
            if self._available:
                executor = self._available.popleft()
                logger.debug("Acquired executor from pool (%d available)", len(self._available))
            else:
                # Create new container if pool exhausted
                logger.warning(
                    "Pool exhausted (%d in use), creating overflow container",
                    len(self._in_use),
                )
                executor = ContainerExecutor(
                    image=self.image,
                    memory_limit=self.memory_limit,
                )
                executor.start()
            self._in_use.add(executor)
            return executor

    def release(self, executor: SandboxExecutor) -> None:
        """Release an executor back to the pool."""
        with self._lock:
            if executor in self._in_use:
                self._in_use.remove(executor)
                self._available.append(executor)

    def discard(self, executor: SandboxExecutor) -> None:
        """Remove an executor from _in_use without returning it to _available.

        Use this for broken executors that should not be reused.
        """
        logger.warning("Discarding broken executor from pool")
        with self._lock:
            self._in_use.discard(executor)

    def __enter__(self) -> "ContainerPool":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.stop()
