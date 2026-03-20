"""LLM-specific exceptions."""

from shesha.exceptions import SheshaError


class LLMError(SheshaError):
    """Base class for LLM errors."""

    pass


class RateLimitError(LLMError):
    """Rate limited by the API (429)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TransientError(LLMError):
    """Temporary failure (5xx, timeout, connection)."""

    pass


class PermanentError(LLMError):
    """Non-retryable failure (4xx except 429)."""

    pass
