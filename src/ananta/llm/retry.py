"""Retry logic with exponential backoff."""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from shesha.llm.exceptions import PermanentError, RateLimitError, TransientError

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 0.1

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = min(
            self.base_delay * (self.exponential_base**attempt),
            self.max_delay,
        )
        jitter_range = delay * self.jitter
        return delay + random.uniform(-jitter_range, jitter_range)


def retry_with_backoff(
    fn: Callable[[], T],
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> T:
    """
    Execute fn with retry on transient/rate-limit errors.

    Args:
        fn: Function to execute
        config: Retry configuration
        on_retry: Optional callback(exception, attempt) for logging

    Returns:
        Result of fn()

    Raises:
        PermanentError: On non-retryable errors
        Last exception: After max retries exhausted
    """
    config = config or RetryConfig()
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return fn()
        except PermanentError:
            raise
        except (RateLimitError, TransientError) as e:
            last_error = e
            if attempt < config.max_retries:
                if on_retry:
                    on_retry(e, attempt)
                time.sleep(config.delay_for_attempt(attempt))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected state: no error recorded")
