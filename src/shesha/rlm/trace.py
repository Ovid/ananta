"""Trace data classes for RLM execution."""

import time
from dataclasses import dataclass, field
from enum import Enum

from shesha.security.redaction import RedactionConfig, redact


class StepType(Enum):
    """Types of steps in an RLM trace."""

    CODE_GENERATED = "code_generated"
    CODE_OUTPUT = "code_output"
    SUBCALL_REQUEST = "subcall_request"
    SUBCALL_RESPONSE = "subcall_response"
    ERROR = "error"
    FINAL_ANSWER = "final_answer"
    VERIFICATION = "verification"
    SEMANTIC_VERIFICATION = "semantic_verification"


@dataclass
class TraceStep:
    """A single step in the RLM execution trace."""

    type: StepType
    content: str
    timestamp: float
    iteration: int
    tokens_used: int | None = None
    duration_ms: int | None = None
    metadata: dict[str, str] | None = None


@dataclass
class TokenUsage:
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.prompt_tokens + self.completion_tokens


@dataclass
class Trace:
    """Full execution trace of an RLM query."""

    steps: list[TraceStep] = field(default_factory=list)

    def add_step(
        self,
        type: StepType,
        content: str,
        iteration: int,
        tokens_used: int | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> TraceStep:
        """Add a step to the trace."""
        step = TraceStep(
            type=type,
            content=content,
            timestamp=time.time(),
            iteration=iteration,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            metadata=metadata,
        )
        self.steps.append(step)
        return step

    def redacted(self, config: RedactionConfig | None = None) -> "Trace":
        """Return a copy with secrets redacted from all steps.

        Args:
            config: Redaction configuration (uses defaults if None)

        Returns:
            New Trace with redacted content
        """
        redacted_steps = []
        for step in self.steps:
            redacted_steps.append(
                TraceStep(
                    type=step.type,
                    content=redact(step.content, config),
                    timestamp=step.timestamp,
                    iteration=step.iteration,
                    tokens_used=step.tokens_used,
                    duration_ms=step.duration_ms,
                    metadata=step.metadata,
                )
            )
        return Trace(steps=redacted_steps)
