"""Secret redaction utilities."""

import re
from dataclasses import dataclass, field


@dataclass
class RedactionConfig:
    """Configuration for secret redaction."""

    patterns: list[re.Pattern[str]] = field(default_factory=list)
    placeholder: str = "[REDACTED]"

    @classmethod
    def default(cls) -> "RedactionConfig":
        """Sensible defaults for common secret patterns."""
        return cls(
            patterns=[
                # API keys (OpenAI, Anthropic, etc.)
                re.compile(r"sk-[a-zA-Z0-9]{20,}"),
                re.compile(r"anthropic-[a-zA-Z0-9-]{20,}"),
                # Bearer tokens
                re.compile(r"Bearer\s+[a-zA-Z0-9._-]{20,}"),
                # Environment variable patterns
                re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+"),
                # AWS keys
                re.compile(r"AKIA[0-9A-Z]{16}"),
                # Base64 credentials (Basic auth)
                re.compile(r"Basic\s+[a-zA-Z0-9+/]{20,}={0,2}"),
                # Private key blocks
                re.compile(r"-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----"),
            ]
        )


def redact(text: str, config: RedactionConfig | None = None) -> str:
    """
    Redact secrets from text using configured patterns.

    Args:
        text: Input text potentially containing secrets
        config: Redaction configuration (uses defaults if None)

    Returns:
        Text with secrets replaced by placeholder
    """
    if config is None:
        config = RedactionConfig.default()

    for pattern in config.patterns:
        text = pattern.sub(config.placeholder, text)
    return text
