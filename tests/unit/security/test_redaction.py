"""Tests for secret redaction."""

import re

from ananta.security.redaction import RedactionConfig, redact


class TestRedact:
    """Tests for redact function."""

    def test_openai_api_key_redacted(self) -> None:
        """OpenAI API keys are redacted."""
        text = "key is sk-abc123def456ghi789jkl012mno345"
        result = redact(text)
        assert "sk-abc123" not in result
        assert "[REDACTED]" in result

    def test_anthropic_api_key_redacted(self) -> None:
        """Anthropic API keys are redacted."""
        text = "anthropic-sk-ant-api03-abc123def456"
        result = redact(text)
        assert "anthropic-sk" not in result
        assert "[REDACTED]" in result

    def test_bearer_token_redacted(self) -> None:
        """Bearer tokens are redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload"
        result = redact(text)
        assert "eyJhbGciOiJ" not in result
        assert "[REDACTED]" in result

    def test_env_var_pattern_redacted(self) -> None:
        """Environment variable patterns are redacted."""
        text = "API_KEY=mysecretvalue123"
        result = redact(text)
        assert "mysecretvalue123" not in result

    def test_aws_access_key_redacted(self) -> None:
        """AWS access keys are redacted."""
        text = "aws_key = AKIAIOSFODNN7EXAMPLE"
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_basic_auth_redacted(self) -> None:
        """Basic auth credentials are redacted."""
        text = "Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQ="
        result = redact(text)
        assert "dXNlcm5hbWU6" not in result

    def test_private_key_header_redacted(self) -> None:
        """Private key headers are redacted."""
        text = "-----BEGIN RSA PRIVATE KEY-----"
        result = redact(text)
        assert "PRIVATE KEY" not in result

    def test_normal_text_unchanged(self) -> None:
        """Normal text without secrets is unchanged."""
        text = "This is just normal text about API design."
        result = redact(text)
        assert result == text

    def test_custom_placeholder(self) -> None:
        """Custom placeholder is used."""
        config = RedactionConfig.default()
        config.placeholder = "[SECRET]"
        text = "sk-abc123def456ghi789jkl012mno345pqr"
        result = redact(text, config)
        assert "[SECRET]" in result
        assert "[REDACTED]" not in result

    def test_custom_patterns(self) -> None:
        """Custom patterns work."""
        config = RedactionConfig(
            patterns=[re.compile(r"secret-\d+")],
            placeholder="[HIDDEN]",
        )
        text = "The code is secret-12345 today"
        result = redact(text, config)
        assert "secret-12345" not in result
        assert "[HIDDEN]" in result
