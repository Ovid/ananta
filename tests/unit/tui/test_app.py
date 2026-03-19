"""Tests for main SheshaTUI app."""

import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Static

from shesha.rlm.engine import QueryResult
from shesha.rlm.trace import StepType, TokenUsage, Trace
from shesha.tui.app import SheshaTUI
from shesha.tui.widgets.completion_popup import CompletionPopup
from shesha.tui.widgets.info_bar import InfoBar
from shesha.tui.widgets.input_area import InputArea
from shesha.tui.widgets.output_area import OutputArea


class TestSheshaTUIComposition:
    """Tests for SheshaTUI app layout."""

    async def test_app_has_four_widgets(self) -> None:
        """App composes output area, info bar, completion popup, and input area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            assert pilot.app.query_one(OutputArea)
            assert pilot.app.query_one(InfoBar)
            assert pilot.app.query_one(CompletionPopup)
            assert pilot.app.query_one(InputArea)

    async def test_builtin_commands_registered(self) -> None:
        """Built-in commands are registered on startup."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            commands = pilot.app._command_registry.list_commands()
            names = [name for name, _desc in commands]
            assert "/help" in names
            assert "/quit" in names
            assert "/write" in names
            assert "/markdown" in names
            assert "/theme" in names

    async def test_register_custom_command(self) -> None:
        """Custom commands can be registered before run."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app.register_command("/custom", lambda args: None, "Custom command")
        async with app.run_test() as pilot:
            commands = pilot.app._command_registry.list_commands()
            names = [name for name, _desc in commands]
            assert "/custom" in names

    async def test_set_group_help_handler(self) -> None:
        """set_group_help_handler is a public method that delegates to CommandRegistry."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        app.register_group("/grp", "A group")
        captured: list[str] = []
        app.set_group_help_handler("/grp", lambda args: captured.append(args))
        async with app.run_test() as pilot:
            resolved = pilot.app._command_registry.resolve("/grp")
            assert resolved is not None
            handler, args, _threaded = resolved
            handler(args)
            assert captured == [""]

    async def test_help_command_shows_output(self) -> None:
        """The /help command adds a message to the output area."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/help"
            # First enter accepts the completion
            await pilot.press("enter")
            await pilot.pause()
            # Second enter submits the command
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            # Should have at least one system message with command list
            statics = output.query("Static")
            assert len(statics) > 0


class TestCompletionIntegration:
    """Tests for slash command auto-complete in SheshaTUI."""

    async def test_typing_slash_shows_completion_popup(self) -> None:
        """Typing '/' shows the completion popup with all commands."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            # Initially hidden
            assert popup.is_visible is False
            # Type a slash
            input_area.text = "/"
            await pilot.pause()
            assert popup.is_visible is True
            assert input_area.completion_active is True

    async def test_completion_popup_filters_as_typing(self) -> None:
        """Popup filters to matching commands as user types."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            # Type '/he' — only /help should match
            input_area.text = "/he"
            await pilot.pause()
            assert popup.is_visible is True
            assert popup.selected_value == "/help"

    async def test_completion_accept_fills_input(self) -> None:
        """Accepting a completion fills the input with the command."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            # Show completions
            input_area.text = "/he"
            await pilot.pause()
            assert popup.selected_value == "/help"
            # Accept
            await pilot.press("enter")
            await pilot.pause()
            assert input_area.text == "/help "
            assert popup.is_visible is False
            assert input_area.completion_active is False

    async def test_completion_popup_hidden_for_non_slash_text(self) -> None:
        """Popup stays hidden for non-slash text."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            popup = pilot.app.query_one(CompletionPopup)
            input_area.text = "hello"
            await pilot.pause()
            assert popup.is_visible is False


class TestFocusToggle:
    """Tests for Tab focus toggling between InputArea and OutputArea."""

    async def test_tab_moves_focus_to_output_area(self) -> None:
        """Tab from InputArea moves focus to OutputArea."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # InputArea has focus on startup
            assert pilot.app.query_one(InputArea).has_focus
            await pilot.press("tab")
            await pilot.pause()
            assert pilot.app.query_one(OutputArea).has_focus

    async def test_tab_moves_focus_back_to_input_area(self) -> None:
        """Tab from OutputArea moves focus back to InputArea."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Move to OutputArea first
            await pilot.press("tab")
            await pilot.pause()
            assert pilot.app.query_one(OutputArea).has_focus
            # Tab again goes back to InputArea
            await pilot.press("tab")
            await pilot.pause()
            assert pilot.app.query_one(InputArea).has_focus

    async def test_input_area_has_focus_on_startup(self) -> None:
        """InputArea has focus when app starts."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            assert pilot.app.query_one(InputArea).has_focus


class TestHelpBar:
    """Tests for the help bar below the input area."""

    async def test_help_bar_exists(self) -> None:
        """App includes a help bar with keyboard hints."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            help_bar = pilot.app.query_one("#help-bar", Static)
            text = str(help_bar.render())
            assert "Tab" in text
            assert "history" in text.lower()
            assert "Esc" in text


class TestHistoryNavigation:
    """Tests for up/down arrow key input history."""

    async def test_up_arrow_fills_previous_input(self) -> None:
        """Up arrow fills the input with the previous history entry."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            # Submit a query (add to history manually since no real query runs)
            pilot.app._input_history.add("first question")
            pilot.app._input_history.add("second question")
            # Up arrow should show most recent
            await pilot.press("up")
            await pilot.pause()
            assert input_area.text == "second question"
            # Up again shows older
            await pilot.press("up")
            await pilot.pause()
            assert input_area.text == "first question"

    async def test_down_arrow_navigates_forward(self) -> None:
        """Down arrow navigates forward through history."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            pilot.app._input_history.add("first")
            pilot.app._input_history.add("second")
            # Go back twice
            await pilot.press("up")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            assert input_area.text == "first"
            # Forward once
            await pilot.press("down")
            await pilot.pause()
            assert input_area.text == "second"

    async def test_down_past_end_clears_input(self) -> None:
        """Down arrow past end of history clears the input."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            pilot.app._input_history.add("query")
            await pilot.press("up")
            await pilot.pause()
            assert input_area.text == "query"
            # Down past end clears
            await pilot.press("down")
            await pilot.pause()
            assert input_area.text == ""


class TestQueryGuard:
    """Tests that new queries are rejected while one is in progress."""

    async def test_query_rejected_while_in_progress(self) -> None:
        """Submitting a query while one is running shows a system message."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            # Simulate a query already running
            pilot.app._query_in_progress = True
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "another question"
            await pilot.press("enter")
            await pilot.pause()
            # Should show a system message about query in progress
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already running" in t.lower() for t in texts)

    async def test_query_not_added_to_history_while_in_progress(self) -> None:
        """A rejected query should not be added to input history."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._query_in_progress = True
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "rejected query"
            await pilot.press("enter")
            await pilot.pause()
            assert "rejected query" not in list(pilot.app._input_history._entries)

    async def test_commands_still_work_while_query_in_progress(self) -> None:
        """Commands like /help should still work during a running query."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._query_in_progress = True
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/help"
            # First enter accepts the completion
            await pilot.press("enter")
            await pilot.pause()
            # Second enter submits the command
            await pilot.press("enter")
            await pilot.pause()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            # Should have command output, not rejection message
            assert len(statics) > 0


class TestIncrementalTokenDisplay:
    """Tests for incremental token updates during query execution."""

    async def test_on_progress_updates_cumulative_tokens(self) -> None:
        """Progress callback with TokenUsage updates app cumulative token fields."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Verify initial state
            assert pilot.app._cumulative_prompt_tokens == 0
            assert pilot.app._cumulative_completion_tokens == 0

            # Simulate a query in progress and call _on_progress from a worker thread
            pilot.app._query_in_progress = True
            pilot.app._query_start_time = 0.0
            pilot.app._last_iteration = 0

            token_usage = TokenUsage(prompt_tokens=500, completion_tokens=100)

            # Use run_worker to call from a different thread (required by call_from_thread)
            def worker_fn() -> None:
                pilot.app._on_progress(StepType.CODE_GENERATED, 0, "some code", token_usage)

            worker = pilot.app.run_worker(worker_fn, thread=True)
            await worker.wait()
            await pilot.pause()

            # Cumulative tokens should be updated
            assert pilot.app._cumulative_prompt_tokens == 500
            assert pilot.app._cumulative_completion_tokens == 100

            # Info bar should reflect the updated tokens
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "500" in line1
            assert "100" in line1

    async def test_query_complete_does_not_double_count_tokens(self) -> None:
        """_on_query_complete must not double-count tokens already reported by _on_progress."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._query_in_progress = True
            pilot.app._query_start_time = 0.0
            pilot.app._query_id = 1

            # Simulate progress callback setting cumulative tokens (as engine does)
            token_usage = TokenUsage(prompt_tokens=500, completion_tokens=100)

            def worker_fn() -> None:
                pilot.app._on_progress(StepType.CODE_GENERATED, 0, "code", token_usage)

            worker = pilot.app.run_worker(worker_fn, thread=True)
            await worker.wait()
            await pilot.pause()

            # Now simulate query completion with the same cumulative token_usage
            result = QueryResult(
                answer="done",
                trace=Trace(),
                token_usage=token_usage,
                execution_time=1.0,
            )
            pilot.app._on_query_complete(1, result, "q")
            await pilot.pause()

            # Should be 500/100, NOT 1000/200 (double-counted)
            assert pilot.app._cumulative_prompt_tokens == 500
            assert pilot.app._cumulative_completion_tokens == 100

    async def test_tokens_accumulate_across_queries(self) -> None:
        """Token totals accumulate across multiple queries in a session."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # First query
            pilot.app._query_in_progress = True
            pilot.app._query_start_time = 0.0
            pilot.app._query_id = 1
            result1 = QueryResult(
                answer="a1",
                trace=Trace(),
                token_usage=TokenUsage(prompt_tokens=200, completion_tokens=40),
                execution_time=1.0,
            )
            pilot.app._on_query_complete(1, result1, "q1")
            await pilot.pause()

            assert pilot.app._cumulative_prompt_tokens == 200
            assert pilot.app._cumulative_completion_tokens == 40

            # Second query — save baseline as _run_query would
            pilot.app._query_in_progress = True
            pilot.app._query_id = 2
            pilot.app._baseline_prompt_tokens = pilot.app._cumulative_prompt_tokens
            pilot.app._baseline_completion_tokens = pilot.app._cumulative_completion_tokens
            result2 = QueryResult(
                answer="a2",
                trace=Trace(),
                token_usage=TokenUsage(prompt_tokens=300, completion_tokens=60),
                execution_time=1.0,
            )
            pilot.app._on_query_complete(2, result2, "q2")
            await pilot.pause()

            # Should be 200+300=500 and 40+60=100
            assert pilot.app._cumulative_prompt_tokens == 500
            assert pilot.app._cumulative_completion_tokens == 100


class TestQueryCancellation:
    """Tests for Esc×2 query cancellation."""

    async def test_double_escape_cancels_query(self) -> None:
        """Double-escape stops a running query and shows Cancelled."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            info_bar = pilot.app.query_one(InfoBar)
            # Simulate a query in progress
            pilot.app._query_in_progress = True
            input_area.query_in_progress = True
            input_area.text = "some text"
            # First escape clears text
            await pilot.press("escape")
            await pilot.pause()
            assert input_area.text == ""
            # Second escape cancels
            await pilot.press("escape")
            await pilot.pause()
            assert pilot.app._query_in_progress is False
            assert input_area.query_in_progress is False
            _, line2 = info_bar._state.render_lines()
            assert "Cancelled" in line2

    async def test_cancellation_bumps_query_id(self) -> None:
        """Cancelling a query increments _query_id so stale workers are ignored."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            id_before = pilot.app._query_id
            # Simulate a query in progress and cancel it
            pilot.app._query_in_progress = True
            pilot.app.query_one(InputArea).query_in_progress = True
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert pilot.app._query_id > id_before

    async def test_stale_worker_result_ignored_after_cancel_and_new_query(self) -> None:
        """A stale worker completing after cancellation doesn't corrupt state."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Simulate: query A started at id=0, then cancelled (id bumped)
            pilot.app._query_in_progress = True
            pilot.app.query_one(InputArea).query_in_progress = True
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            # Now the stale worker tries to post progress — should be ignored
            pilot.app._on_progress(StepType.CODE_GENERATED, 0, "stale code")
            assert pilot.app._last_iteration == 0  # Not updated

    async def test_stale_worker_completion_ignored_after_new_query(self) -> None:
        """A stale worker from query A is ignored even after query B starts."""
        project = MagicMock()
        # Make project.query block so _run_query doesn't complete immediately
        project.query.side_effect = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("should not be called in this test")
        )
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Simulate query A in progress, then cancel it
            pilot.app._query_in_progress = True
            pilot.app.query_one(InputArea).query_in_progress = True
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            # Now query A's stale worker tries to post a result.
            # With the old boolean flag and a new query having reset it,
            # this would corrupt state. With query_id, it's always safe.
            stale_result = QueryResult(
                answer="stale answer",
                execution_time=1.0,
                token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
                trace=Trace(steps=[]),
            )
            output = pilot.app.query_one(OutputArea)
            statics_before = len(output.query("Static"))
            stale_query_id = 0  # ID before cancellation bumped it
            pilot.app._on_query_complete(stale_query_id, stale_result, "stale question")
            statics_after = len(output.query("Static"))
            assert statics_after == statics_before

    async def test_cancel_sets_cancel_event(self) -> None:
        """Double-escape sets the cancel_event on the running query."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Set up a cancel_event as if a query were running
            cancel_event = threading.Event()
            pilot.app._cancel_event = cancel_event
            pilot.app._query_in_progress = True
            pilot.app.query_one(InputArea).query_in_progress = True
            # First escape clears text (if any), second cancels
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            # The cancel_event should now be set
            assert cancel_event.is_set()

    async def test_query_runner_passes_cancel_event(self) -> None:
        """_make_query_runner passes cancel_event to project.query."""
        project = MagicMock()
        project.query.return_value = QueryResult(
            answer="ok",
            trace=Trace(steps=[]),
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            execution_time=0.1,
        )
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Create a cancel event and assign it
            cancel_event = threading.Event()
            pilot.app._cancel_event = cancel_event
            # Capture query_id at runner creation, then bump it
            # so the runner skips call_from_thread (stale check)
            runner = pilot.app._make_query_runner("question", "question")
            pilot.app._query_id += 1
            runner()
            # Verify cancel_event was passed to project.query
            _, kwargs = project.query.call_args
            assert kwargs.get("cancel_event") is cancel_event

    async def test_query_runner_captures_cancel_event_at_creation(self) -> None:
        """Runner uses the cancel_event from creation time, not call time.

        If _cancel_event is replaced (by a new query starting), the old
        runner must still reference the original event, not the new one.
        """
        project = MagicMock()
        project.query.return_value = QueryResult(
            answer="ok",
            trace=Trace(steps=[]),
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            execution_time=0.1,
        )
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            original_event = threading.Event()
            pilot.app._cancel_event = original_event
            runner = pilot.app._make_query_runner("question", "question")

            # Simulate a new query replacing the cancel event
            new_event = threading.Event()
            pilot.app._cancel_event = new_event
            pilot.app._query_id += 1

            runner()
            _, kwargs = project.query.call_args
            # Must use the ORIGINAL event, not the new one
            assert kwargs.get("cancel_event") is original_event
            assert kwargs.get("cancel_event") is not new_event


class TestAnalysisShortcutTokenDisplay:
    """Tests that analysis shortcut answers update token counts in the info bar."""

    async def test_shortcut_answer_updates_token_count(self) -> None:
        """When shortcut answers a query, token counts appear in the info bar."""
        from shesha.analysis.shortcut import ShortcutResult

        project = MagicMock()
        app = SheshaTUI(
            project=project,
            project_name="test",
            model="test-model",
            api_key="key",
        )
        async with app.run_test() as pilot:
            pilot.app._analysis_context = "Analysis: A web framework."

            def mock_qws(**kwargs):
                return ShortcutResult(
                    answer="Shortcut answer", prompt_tokens=200, completion_tokens=50
                )

            with patch("shesha.tui.app.query_with_shortcut", mock_qws):
                pilot.app._run_query("What does this do?")
                await pilot.app._worker_handle.wait()
                await pilot.pause()

            # Cumulative tokens should reflect shortcut usage
            assert pilot.app._cumulative_prompt_tokens == 200
            assert pilot.app._cumulative_completion_tokens == 50

            # Info bar should display the token counts
            info_bar = pilot.app.query_one(InfoBar)
            line1, _ = info_bar._state.render_lines()
            assert "200" in line1
            assert "50" in line1

    async def test_shortcut_answer_records_tokens_in_session(self) -> None:
        """Shortcut session stats include token counts, matching normal query path."""
        from shesha.analysis.shortcut import ShortcutResult

        project = MagicMock()
        app = SheshaTUI(
            project=project,
            project_name="test",
            model="test-model",
            api_key="key",
        )
        async with app.run_test() as pilot:
            pilot.app._analysis_context = "Analysis: A web framework."

            def mock_qws(**kwargs):
                return ShortcutResult(
                    answer="Shortcut answer", prompt_tokens=200, completion_tokens=50
                )

            with patch("shesha.tui.app.query_with_shortcut", mock_qws):
                pilot.app._run_query("What does this do?")
                await pilot.app._worker_handle.wait()
                await pilot.pause()

            # Session stats should include token counts
            assert len(pilot.app._session._history) == 1
            _q, _a, stats = pilot.app._session._history[0]
            assert "prompt: 200" in stats
            assert "completion: 50" in stats

    async def test_shortcut_answer_shows_thought_time(self) -> None:
        """Shortcut answer displays 'Thought for N seconds' above the response."""
        from shesha.analysis.shortcut import ShortcutResult

        project = MagicMock()
        app = SheshaTUI(
            project=project,
            project_name="test",
            model="test-model",
            api_key="key",
        )
        async with app.run_test() as pilot:
            pilot.app._analysis_context = "Analysis: A web framework."

            def mock_qws(**kwargs):
                return ShortcutResult(
                    answer="Shortcut answer", prompt_tokens=200, completion_tokens=50
                )

            with patch("shesha.tui.app.query_with_shortcut", mock_qws):
                pilot.app._run_query("What does this do?")
                await pilot.app._worker_handle.wait()
                await pilot.pause()

            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            # Should have a "Thought for" indicator
            assert any("Thought for" in t for t in texts)
            # Should also have the "Answered from codebase analysis." note
            # (rendered as markdown or static, check both)
            all_text = " ".join(texts)
            markdown_widgets = output.query("Markdown")
            md_texts = [str(m.render()) for m in markdown_widgets]
            all_text += " ".join(md_texts)
            assert "Answered from codebase analysis." in all_text


class TestAnalysisShortcutHistoryContext:
    """Analysis shortcut must receive conversation history with the question."""

    async def test_shortcut_receives_history_prefix(self) -> None:
        """When conversation history exists, shortcut question includes it."""
        from shesha.analysis.shortcut import ShortcutResult

        project = MagicMock()
        app = SheshaTUI(
            project=project,
            project_name="test",
            model="test-model",
            api_key="key",
        )
        async with app.run_test() as pilot:
            # Set up analysis context and conversation history
            pilot.app._analysis_context = "Analysis: This is a web framework."
            pilot.app._session.add_exchange(
                "What does module A do?", "Module A handles routing.", ""
            )

            captured_questions: list[str] = []

            def mock_qws(**kwargs):
                captured_questions.append(kwargs["question"])
                return ShortcutResult(
                    answer="Shortcut answer", prompt_tokens=100, completion_tokens=25
                )

            with patch("shesha.tui.app.query_with_shortcut", mock_qws):
                pilot.app._run_query("What about module B?")
                await pilot.app._worker_handle.wait()
                await pilot.pause()

            assert len(captured_questions) == 1
            q = captured_questions[0]
            # Must include conversation history
            assert "What does module A do?" in q
            assert "Module A handles routing." in q
            # Must include the current question
            assert "What about module B?" in q


class TestWriteOverwriteProtection:
    """Tests for /write overwrite protection with force flag."""

    async def test_write_force_flag_strips_bang(self, tmp_path: Path) -> None:
        """Trailing ! is stripped and write_transcript is called with clean filename."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            # Add an exchange so write is allowed
            pilot.app._session.add_exchange("q", "a", "stats")
            # Use tmp_path so we don't pollute cwd
            target = tmp_path / "notes.md"
            with patch.object(
                pilot.app._session, "write_transcript", return_value=str(target)
            ) as mock_write:
                pilot.app._cmd_write(f"{target.with_suffix('')}!")
            mock_write.assert_called_once_with(str(target))

    async def test_write_force_flag_with_md_extension(self, tmp_path: Path) -> None:
        """notes.md! results in write_transcript('notes.md')."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "stats")
            target = tmp_path / "notes.md"
            with patch.object(
                pilot.app._session, "write_transcript", return_value=str(target)
            ) as mock_write:
                pilot.app._cmd_write(f"{target}!")
            mock_write.assert_called_once_with(str(target))

    async def test_write_blocked_when_file_exists(self, tmp_path: Path) -> None:
        """Existing file blocks write and shows 'already exists' message."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "stats")
            # Create the file on disk
            target = tmp_path / "notes.md"
            target.write_text("original content")
            with patch.object(pilot.app._session, "write_transcript") as mock_write:
                pilot.app._cmd_write(str(target))
            # write_transcript should NOT have been called
            mock_write.assert_not_called()
            # Should show "already exists" message
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already exists" in t for t in texts)
            # Original file should be untouched
            assert target.read_text() == "original content"

    async def test_write_force_overwrites_existing(self, tmp_path: Path) -> None:
        """Force flag bypasses existence check and writes."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "stats")
            target = tmp_path / "notes.md"
            target.write_text("original content")
            with patch.object(
                pilot.app._session, "write_transcript", return_value=str(target)
            ) as mock_write:
                pilot.app._cmd_write(f"{target}!")
            mock_write.assert_called_once_with(str(target))

    async def test_write_shows_actual_filename_on_collision(self, tmp_path: Path) -> None:
        """Case-insensitive collision shows actual on-disk name."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "stats")
            # Create NOTES.md on disk
            actual_file = tmp_path / "NOTES.md"
            actual_file.write_text("content")
            # Detect case-insensitive FS *before* _cmd_write (which would
            # create the file on case-sensitive FS, making exists() true).
            requested = tmp_path / "notes.md"
            case_insensitive = requested.exists()
            pilot.app._cmd_write(str(requested))
            if case_insensitive:
                output = pilot.app.query_one(OutputArea)
                statics = output.query("Static")
                texts = [str(s.render()) for s in statics]
                assert any("NOTES.md" in t and "already exists" in t for t in texts)

    async def test_write_iterdir_permission_error_falls_back(self, tmp_path: Path) -> None:
        """PermissionError from iterdir() still shows warning, not a crash."""
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "stats")
            target = tmp_path / "notes.md"
            target.write_text("content")
            with patch.object(
                type(target.parent), "iterdir", side_effect=PermissionError("denied")
            ):
                pilot.app._cmd_write(str(target))
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already exists" in t for t in texts)

    async def test_write_auto_name_blocked_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auto-generated filename collision is blocked."""
        monkeypatch.chdir(tmp_path)
        project = MagicMock()
        app = SheshaTUI(project=project, project_name="test")
        async with app.run_test() as pilot:
            pilot.app._session.add_exchange("q", "a", "stats")
            frozen = datetime(2025, 6, 15, 14, 30, 45)
            auto_name = f"session-{frozen.strftime('%Y-%m-%d-%H%M%S')}.md"
            # Create the auto-generated file in tmp_path
            auto_path = tmp_path / auto_name
            auto_path.write_text("existing")
            with (
                patch("shesha.tui.app.datetime") as mock_dt,
                patch.object(pilot.app._session, "write_transcript") as mock_write,
            ):
                mock_dt.now.return_value = frozen
                mock_dt.side_effect = datetime
                pilot.app._cmd_write("")
            mock_write.assert_not_called()
            output = pilot.app.query_one(OutputArea)
            statics = output.query("Static")
            texts = [str(s.render()) for s in statics]
            assert any("already exists" in t for t in texts)
            assert any(auto_name in t for t in texts)
