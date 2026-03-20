"""Tests for retry logic."""

from unittest.mock import MagicMock

import pytest

from ananta.llm.exceptions import PermanentError, RateLimitError, TransientError
from ananta.llm.retry import RetryConfig, retry_with_backoff


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_values(self) -> None:
        """Default config has sensible values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter == 0.1

    def test_delay_for_attempt_exponential(self) -> None:
        """Delay increases exponentially."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=0.0)
        assert config.delay_for_attempt(0) == 1.0
        assert config.delay_for_attempt(1) == 2.0
        assert config.delay_for_attempt(2) == 4.0

    def test_delay_respects_max(self) -> None:
        """Delay is capped at max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=0.0)
        assert config.delay_for_attempt(10) == 5.0


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    def test_success_no_retry(self) -> None:
        """Successful call doesn't retry."""
        fn = MagicMock(return_value="success")
        result = retry_with_backoff(fn, RetryConfig(max_retries=3))
        assert result == "success"
        assert fn.call_count == 1

    def test_transient_error_retries(self) -> None:
        """TransientError triggers retry."""
        fn = MagicMock(side_effect=[TransientError("fail"), "success"])
        config = RetryConfig(max_retries=3, base_delay=0.001)
        result = retry_with_backoff(fn, config)
        assert result == "success"
        assert fn.call_count == 2

    def test_rate_limit_error_retries(self) -> None:
        """RateLimitError triggers retry."""
        fn = MagicMock(side_effect=[RateLimitError("limited"), "success"])
        config = RetryConfig(max_retries=3, base_delay=0.001)
        result = retry_with_backoff(fn, config)
        assert result == "success"
        assert fn.call_count == 2

    def test_permanent_error_no_retry(self) -> None:
        """PermanentError does not retry."""
        fn = MagicMock(side_effect=PermanentError("bad request"))
        config = RetryConfig(max_retries=3)
        with pytest.raises(PermanentError):
            retry_with_backoff(fn, config)
        assert fn.call_count == 1

    def test_max_retries_exhausted(self) -> None:
        """Raises after max retries exhausted."""
        fn = MagicMock(side_effect=TransientError("always fails"))
        config = RetryConfig(max_retries=2, base_delay=0.001)
        with pytest.raises(TransientError):
            retry_with_backoff(fn, config)
        assert fn.call_count == 3  # initial + 2 retries

    def test_on_retry_callback(self) -> None:
        """on_retry callback is called."""
        fn = MagicMock(side_effect=[TransientError("fail"), "success"])
        on_retry = MagicMock()
        config = RetryConfig(max_retries=3, base_delay=0.001)
        retry_with_backoff(fn, config, on_retry=on_retry)
        assert on_retry.call_count == 1
