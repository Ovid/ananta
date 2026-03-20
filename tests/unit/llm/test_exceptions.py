"""Tests for LLM exception hierarchy."""

import pytest

from ananta.exceptions import AnantaError
from ananta.llm.exceptions import LLMError, PermanentError, RateLimitError, TransientError


class TestLLMExceptionHierarchy:
    """Tests for LLM exception classes."""

    def test_llm_error_is_base(self) -> None:
        """LLMError is the base exception."""
        error = LLMError("test")
        assert isinstance(error, Exception)

    def test_llm_error_inherits_ananta_error(self) -> None:
        """LLMError inherits from AnantaError for unified exception handling."""
        error = LLMError("test")
        assert isinstance(error, AnantaError)

    def test_llm_subtypes_catchable_by_ananta_error(self) -> None:
        """All LLM exceptions are catchable via AnantaError."""
        for exc_class in [LLMError, RateLimitError, TransientError, PermanentError]:
            with pytest.raises(AnantaError):
                raise exc_class("test")

    def test_rate_limit_error_inherits(self) -> None:
        """RateLimitError inherits from LLMError."""
        error = RateLimitError("rate limited")
        assert isinstance(error, LLMError)

    def test_rate_limit_error_has_retry_after(self) -> None:
        """RateLimitError can store retry_after."""
        error = RateLimitError("rate limited", retry_after=30.0)
        assert error.retry_after == 30.0

    def test_transient_error_inherits(self) -> None:
        """TransientError inherits from LLMError."""
        error = TransientError("timeout")
        assert isinstance(error, LLMError)

    def test_permanent_error_inherits(self) -> None:
        """PermanentError inherits from LLMError."""
        error = PermanentError("invalid request")
        assert isinstance(error, LLMError)

    def test_exceptions_are_catchable_by_base(self) -> None:
        """All exceptions are catchable by LLMError."""
        for exc_class in [RateLimitError, TransientError, PermanentError]:
            with pytest.raises(LLMError):
                raise exc_class("test")
