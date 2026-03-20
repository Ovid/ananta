"""Tests for TUI info bar widget."""

from unittest.mock import MagicMock

from ananta.tui.app import AnantaTUI
from ananta.tui.widgets.info_bar import InfoBar, InfoBarState, abbreviate_model


class TestInfoBarState:
    """Tests for InfoBarState data model (no Textual dependency)."""

    def test_initial_state(self) -> None:
        """Initial state shows project name and zero tokens."""
        state = InfoBarState(project_name="barsoom", model="")
        line1, line2 = state.render_lines()
        assert "barsoom" in line1
        assert "0" in line1
        assert "Ready" in line2

    def test_update_tokens(self) -> None:
        """Token counts update after set_tokens."""
        state = InfoBarState(project_name="test", model="")
        state.set_tokens(prompt=1000, completion=200)
        line1, _ = state.render_lines()
        assert "1,200" in line1
        assert "1,000" in line1
        assert "200" in line1

    def test_set_phase_thinking(self) -> None:
        """Phase shows Thinking with elapsed time at end."""
        state = InfoBarState(project_name="test", model="")
        state.set_thinking(elapsed=0.5)
        _, line2 = state.render_lines()
        assert "Thinking" in line2
        assert "| Time: 0.5s" in line2
        # Timer must not appear inline before the phase description
        phase_part = line2.split("|")[0]
        assert "0.5s" not in phase_part

    def test_set_phase_progress(self) -> None:
        """Phase shows iteration and step name with time at end."""
        state = InfoBarState(project_name="test", model="")
        state.set_progress(elapsed=13.7, iteration=3, step="Sub-LLM query")
        _, line2 = state.render_lines()
        assert "Iteration 3" in line2
        assert "Sub-LLM query" in line2
        assert "| Time: 13.7s" in line2
        # Timer must not appear inline before the phase description
        phase_part = line2.split("|")[0]
        assert "13.7s" not in phase_part

    def test_set_phase_done(self) -> None:
        """Phase shows Done with iteration count and time at end."""
        state = InfoBarState(project_name="test", model="")
        state.set_done(elapsed=52.3, iterations=3)
        _, line2 = state.render_lines()
        assert "Done" in line2
        assert "3 iterations" in line2
        assert "| Time: 52.3s" in line2
        # Timer must not appear inline before the phase description
        phase_part = line2.split("|")[0]
        assert "52.3s" not in phase_part

    def test_set_phase_cancelled(self) -> None:
        """Phase shows Cancelled."""
        state = InfoBarState(project_name="test", model="")
        state.set_cancelled()
        _, line2 = state.render_lines()
        assert "Cancelled" in line2

    def test_reset_to_ready(self) -> None:
        """Reset returns to Ready state."""
        state = InfoBarState(project_name="test", model="")
        state.set_thinking(elapsed=1.0)
        state.reset()
        _, line2 = state.render_lines()
        assert "Ready" in line2

    def test_model_displayed_on_line1(self) -> None:
        """Model name appears on line 1 between project and tokens."""
        state = InfoBarState(project_name="test", model="claude-sonnet-4-20250514")
        line1, _ = state.render_lines()
        assert "Model: claude-sonnet-4" in line1
        assert "Project: test" in line1

    def test_model_abbreviated_in_display(self) -> None:
        """Model name has date suffix stripped in display."""
        state = InfoBarState(project_name="test", model="gpt-4o-2024-05-13")
        line1, _ = state.render_lines()
        assert "Model: gpt-4o" in line1

    def test_model_no_date_suffix_unchanged(self) -> None:
        """Model without date suffix displayed as-is."""
        state = InfoBarState(project_name="test", model="gemini-1.5-pro")
        line1, _ = state.render_lines()
        assert "Model: gemini-1.5-pro" in line1


class TestAbbreviateModel:
    """Tests for abbreviate_model() date suffix stripping."""

    def test_strips_yyyymmdd_suffix(self) -> None:
        """Strips -YYYYMMDD date suffix."""
        assert abbreviate_model("claude-sonnet-4-20250514") == "claude-sonnet-4"

    def test_strips_yyyy_mm_dd_suffix(self) -> None:
        """Strips -YYYY-MM-DD date suffix."""
        assert abbreviate_model("gpt-4o-2024-05-13") == "gpt-4o"

    def test_no_date_suffix_unchanged(self) -> None:
        """Model without date suffix returned unchanged."""
        assert abbreviate_model("gemini-1.5-pro") == "gemini-1.5-pro"

    def test_empty_string(self) -> None:
        """Empty string returned unchanged."""
        assert abbreviate_model("") == ""

    def test_only_date_pattern(self) -> None:
        """String that is only a date pattern still strips it."""
        assert abbreviate_model("model-20250514") == "model"


class TestInfoBarProjectNameUpdate:
    """Tests for InfoBar.update_project_name() method."""

    def test_update_project_name_changes_state(self) -> None:
        """Setting project_name on state changes render_lines output."""
        state = InfoBarState(project_name="old", model="gpt-4o")
        state.project_name = "new-topic"
        line1, _ = state.render_lines()
        assert "new-topic" in line1
        assert "old" not in line1

    async def test_info_bar_update_project_name_widget(self) -> None:
        """update_project_name() updates the widget state."""
        app = AnantaTUI(project=MagicMock(), project_name="test")
        async with app.run_test() as pilot:
            info_bar = pilot.app.query_one(InfoBar)
            info_bar.update_project_name("new-topic")
            line1, _ = info_bar._state.render_lines()
            assert "new-topic" in line1
