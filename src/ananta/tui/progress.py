"""Progress display helpers for TUI."""

from shesha.rlm.trace import StepType

_STEP_NAMES: dict[StepType, str] = {
    StepType.CODE_GENERATED: "Generating code",
    StepType.CODE_OUTPUT: "Executing code",
    StepType.SUBCALL_REQUEST: "Sub-LLM query",
    StepType.SUBCALL_RESPONSE: "Sub-LLM response",
    StepType.FINAL_ANSWER: "Final answer",
    StepType.ERROR: "Error",
    StepType.VERIFICATION: "Verification",
    StepType.SEMANTIC_VERIFICATION: "Semantic verification",
}


def step_display_name(step_type: StepType) -> str:
    """Get human-readable display name for a step type."""
    return _STEP_NAMES.get(step_type, step_type.value)
