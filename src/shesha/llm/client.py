"""LLM client wrapper using LiteLLM."""

from dataclasses import dataclass
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    Timeout,
)
from litellm.exceptions import RateLimitError as LiteLLMRateLimit

from shesha.llm.exceptions import PermanentError, RateLimitError, TransientError
from shesha.llm.retry import RetryConfig, retry_with_backoff


@dataclass
class LLMResponse:
    """Response from an LLM completion."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    raw_response: Any = None


# Default timeout for LLM API calls (seconds). Prevents infinite hangs
# when the API connection is established but the response never arrives.
DEFAULT_TIMEOUT = 300


class LLMClient:
    """Wrapper around LiteLLM for unified LLM access."""

    def __init__(
        self,
        model: str,
        system_prompt: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        """Initialize the LLM client."""
        self.model = model
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.retry_config = retry_config or RetryConfig()
        self.timeout = timeout
        self.extra_kwargs = kwargs

    def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request to the LLM with automatic retry."""
        full_messages = list(messages)
        if self.system_prompt:
            full_messages.insert(0, {"role": "system", "content": self.system_prompt})

        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "timeout": self.timeout,
            **self.extra_kwargs,
            **kwargs,
        }
        if self.api_key:
            call_kwargs["api_key"] = self.api_key

        def _do_request() -> LLMResponse:
            try:
                response = litellm.completion(**call_kwargs)
                return LLMResponse(
                    content=response.choices[0].message.content,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    raw_response=response,
                )
            except LiteLLMRateLimit as e:
                raise RateLimitError(str(e)) from e
            except (APIConnectionError, Timeout) as e:
                raise TransientError(str(e)) from e
            except AuthenticationError as e:
                raise PermanentError(str(e)) from e
            except APIError as e:
                if hasattr(e, "status_code") and e.status_code and e.status_code >= 500:
                    raise TransientError(str(e)) from e
                raise PermanentError(str(e)) from e

        return retry_with_backoff(_do_request, self.retry_config)
