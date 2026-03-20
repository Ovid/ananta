"""Tests for trace data classes."""

from ananta.rlm.trace import StepType, TokenUsage, Trace, TraceStep


def test_trace_step_creation():
    """TraceStep stores step information."""
    step = TraceStep(
        type=StepType.CODE_GENERATED,
        content="print('hello')",
        timestamp=1234567890.0,
        iteration=0,
        tokens_used=100,
        duration_ms=None,
    )
    assert step.type == StepType.CODE_GENERATED
    assert step.content == "print('hello')"
    assert step.iteration == 0


def test_trace_accumulates_steps():
    """Trace accumulates multiple steps."""
    trace = Trace()
    trace.add_step(
        type=StepType.CODE_GENERATED,
        content="code",
        iteration=0,
    )
    trace.add_step(
        type=StepType.CODE_OUTPUT,
        content="output",
        iteration=0,
    )
    assert len(trace.steps) == 2


def test_token_usage_total():
    """TokenUsage calculates total correctly."""
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    assert usage.total_tokens == 150


class TestTraceRedaction:
    """Tests for trace redaction."""

    def test_redacted_returns_new_trace(self) -> None:
        """redacted() returns a new Trace instance."""
        trace = Trace()
        trace.add_step(StepType.CODE_GENERATED, "code", 0)
        redacted = trace.redacted()
        assert redacted is not trace
        assert len(redacted.steps) == len(trace.steps)

    def test_redacts_secrets_in_content(self) -> None:
        """Secrets in step content are redacted."""
        trace = Trace()
        trace.add_step(
            StepType.CODE_OUTPUT,
            "API key is sk-abc123def456ghi789jkl012mno345pqr",
            0,
        )
        redacted = trace.redacted()
        assert "sk-abc123" not in redacted.steps[0].content
        assert "[REDACTED]" in redacted.steps[0].content

    def test_preserves_step_metadata(self) -> None:
        """Step metadata is preserved after redaction."""
        trace = Trace()
        trace.add_step(
            StepType.CODE_GENERATED,
            "secret: sk-abc123def456ghi789jkl012mno345pqr",
            iteration=5,
            tokens_used=100,
            duration_ms=500,
        )
        redacted = trace.redacted()
        step = redacted.steps[0]
        assert step.type == StepType.CODE_GENERATED
        assert step.iteration == 5
        assert step.tokens_used == 100
        assert step.duration_ms == 500

    def test_preserves_metadata_dict(self) -> None:
        """Step metadata dict (e.g. final_source) is preserved after redaction."""
        trace = Trace()
        trace.add_step(
            StepType.FINAL_ANSWER,
            "the answer",
            iteration=3,
            metadata={"final_source": "code_block"},
        )
        redacted = trace.redacted()
        step = redacted.steps[0]
        assert step.metadata == {"final_source": "code_block"}

    def test_custom_redaction_config(self) -> None:
        """Custom redaction config is respected."""
        import re

        trace = Trace()
        trace.add_step(StepType.CODE_OUTPUT, "custom-secret-123", 0)

        from ananta.security.redaction import RedactionConfig

        config = RedactionConfig(
            patterns=[re.compile(r"custom-secret-\d+")],
            placeholder="[HIDDEN]",
        )
        redacted = trace.redacted(config)
        assert "custom-secret-123" not in redacted.steps[0].content
        assert "[HIDDEN]" in redacted.steps[0].content


class TestVerificationStepType:
    """Tests for VERIFICATION step type."""

    def test_verification_step_type_exists(self) -> None:
        """StepType.VERIFICATION exists."""
        assert StepType.VERIFICATION.value == "verification"

    def test_trace_can_add_verification_step(self) -> None:
        """Trace can add a VERIFICATION step."""
        trace = Trace()
        step = trace.add_step(
            type=StepType.VERIFICATION,
            content="verification result json",
            iteration=0,
        )
        assert step.type == StepType.VERIFICATION
        assert len(trace.steps) == 1
