"""Tests for TUI progress helpers."""

from ananta.rlm.trace import StepType
from ananta.tui.progress import step_display_name


class TestStepDisplayName:
    """Tests for step_display_name."""

    def test_code_generated(self) -> None:
        assert step_display_name(StepType.CODE_GENERATED) == "Generating code"

    def test_code_output(self) -> None:
        assert step_display_name(StepType.CODE_OUTPUT) == "Executing code"

    def test_subcall_request(self) -> None:
        assert step_display_name(StepType.SUBCALL_REQUEST) == "Sub-LLM query"

    def test_subcall_response(self) -> None:
        assert step_display_name(StepType.SUBCALL_RESPONSE) == "Sub-LLM response"

    def test_final_answer(self) -> None:
        assert step_display_name(StepType.FINAL_ANSWER) == "Final answer"

    def test_error(self) -> None:
        assert step_display_name(StepType.ERROR) == "Error"

    def test_verification(self) -> None:
        assert step_display_name(StepType.VERIFICATION) == "Verification"

    def test_semantic_verification(self) -> None:
        assert step_display_name(StepType.SEMANTIC_VERIFICATION) == "Semantic verification"
