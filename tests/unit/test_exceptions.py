"""Tests for exception classes."""

from ananta.exceptions import (
    AnantaError,
    AuthenticationError,
    EngineNotConfiguredError,
    RepoIngestError,
    TraceWriteError,
)


class TestRepoExceptions:
    """Tests for repository-related exceptions."""

    def test_authentication_error_message(self):
        """AuthenticationError formats message with URL."""
        err = AuthenticationError("https://github.com/org/private-repo")
        assert "private-repo" in str(err)
        assert "token" in str(err).lower()

    def test_repo_ingest_error_preserves_cause(self):
        """RepoIngestError preserves the original cause."""
        cause = RuntimeError("git clone failed")
        err = RepoIngestError("https://github.com/org/repo", cause)
        assert err.__cause__ is cause
        assert "https://github.com/org/repo" in str(err)


class TestTraceWriteError:
    """Tests for TraceWriteError."""

    def test_is_subclass_of_ananta_error(self):
        """TraceWriteError is a AnantaError subclass."""
        assert issubclass(TraceWriteError, AnantaError)

    def test_accepts_message(self):
        """TraceWriteError can take a custom message."""
        err = TraceWriteError("disk full")
        assert "disk full" in str(err)


class TestEngineNotConfiguredError:
    """Tests for EngineNotConfiguredError."""

    def test_is_subclass_of_ananta_error(self):
        """EngineNotConfiguredError is a AnantaError subclass."""
        assert issubclass(EngineNotConfiguredError, AnantaError)

    def test_default_message_mentions_engine(self):
        """EngineNotConfiguredError has default message mentioning engine."""
        err = EngineNotConfiguredError()
        assert "engine" in str(err).lower()
