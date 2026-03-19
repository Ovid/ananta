"""Tests for analysis shortcut — skip RLM when analysis can answer."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from shesha.analysis.shortcut import (
    _SYSTEM_PROMPT,
    ShortcutResult,
    query_with_shortcut,
    try_answer_from_analysis,
)
from shesha.llm.exceptions import PermanentError
from shesha.rlm.engine import QueryResult
from shesha.rlm.trace import TokenUsage, Trace


class TestTryAnswerFromAnalysis:
    """Tests for try_answer_from_analysis()."""

    def test_returns_answer_when_llm_can_answer(self):
        """When LLM returns a real answer, function returns answer with token counts."""
        classifier_response = MagicMock()
        classifier_response.content = "ANALYSIS_OK"
        classifier_response.prompt_tokens = 15
        classifier_response.completion_tokens = 3

        answer_response = MagicMock()
        answer_response.content = "This codebase implements a web framework."
        answer_response.prompt_tokens = 100
        answer_response.completion_tokens = 20

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            classifier_client = MagicMock()
            classifier_client.complete.return_value = classifier_response
            answer_client = MagicMock()
            answer_client.complete.return_value = answer_response
            mock_cls.side_effect = [classifier_client, answer_client]
            result = try_answer_from_analysis(
                question="What does this codebase do?",
                analysis_context="Overview: A web framework...",
                model="test-model",
                api_key="test-key",
            )

        # Totals include classifier (15+3) + answer (100+20)
        assert result == ("This codebase implements a web framework.", 115, 23)

    def test_returns_none_when_need_deeper(self):
        """When LLM returns NEED_DEEPER, function returns None."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = try_answer_from_analysis(
                question="Find race conditions in the executor",
                analysis_context="Overview: A web framework...",
                model="test-model",
                api_key="test-key",
            )

        assert result is None

    def test_returns_none_when_need_deeper_with_whitespace(self):
        """NEED_DEEPER with trailing whitespace still returns None."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER\n"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = try_answer_from_analysis(
                question="Any question",
                analysis_context="Some analysis",
                model="test-model",
                api_key="test-key",
            )

        assert result is None

    def test_returns_none_when_need_deeper_with_trailing_punctuation(self):
        """NEED_DEEPER with trailing punctuation still returns None."""
        for suffix in [".", "!", ".\n", ". ", ".\nI need more context."]:
            mock_response = MagicMock()
            mock_response.content = f"NEED_DEEPER{suffix}"
            mock_response.prompt_tokens = 50
            mock_response.completion_tokens = 10

            with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
                mock_cls.return_value.complete.return_value = mock_response
                result = try_answer_from_analysis(
                    question="Any question",
                    analysis_context="Some analysis",
                    model="test-model",
                    api_key="test-key",
                )

            assert result is None, f"NEED_DEEPER{suffix!r} should return None"

    def test_returns_none_when_analysis_context_is_none(self):
        """No analysis context -> None immediately, no LLM call."""
        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context=None,
                model="test-model",
                api_key="test-key",
            )

        mock_cls.assert_not_called()
        assert result is None

    def test_returns_none_when_analysis_context_is_empty(self):
        """Empty string analysis context -> None immediately, no LLM call."""
        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context="",
                model="test-model",
                api_key="test-key",
            )

        mock_cls.assert_not_called()
        assert result is None

    def test_wraps_analysis_in_untrusted_tags(self):
        """Prompt sent to LLM wraps analysis in <untrusted_document_content> tags."""
        mock_response = MagicMock()
        mock_response.content = "Some answer"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.complete.return_value = mock_response
            try_answer_from_analysis(
                question="What does this do?",
                analysis_context="Overview: A web framework...",
                model="test-model",
                api_key="test-key",
                boundary="UNTRUSTED_CONTENT_testboundary12345678",
            )

        # Check the user message sent to complete()
        call_args = mock_client.complete.call_args
        messages = call_args[0][0]
        user_content = messages[0]["content"]
        assert "_BEGIN" in user_content
        assert "_END" in user_content
        assert "Overview: A web framework..." in user_content

    def test_returns_stripped_answer(self):
        """Answer is stripped of leading/trailing whitespace."""
        mock_response = MagicMock()
        mock_response.content = "  The answer is Flask.\n"
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 20

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = try_answer_from_analysis(
                question="What framework?",
                analysis_context="Overview: Uses Flask...",
                model="test-model",
                api_key="test-key",
            )

        assert result is not None
        answer, _, _ = result
        assert answer == "The answer is Flask."

    def test_returns_none_on_llm_error(self):
        """LLM exception -> None (graceful fallback)."""
        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.side_effect = Exception("API error")
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context="Some analysis",
                model="test-model",
                api_key="test-key",
            )

        assert result is None

    def test_permanent_error_propagates(self):
        """PermanentError (e.g. auth failure) must not be swallowed."""
        classifier_response = MagicMock()
        classifier_response.content = "ANALYSIS_OK"
        classifier_response.prompt_tokens = 5
        classifier_response.completion_tokens = 1

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            classifier_client = MagicMock()
            classifier_client.complete.return_value = classifier_response
            answer_client = MagicMock()
            answer_client.complete.side_effect = PermanentError("Invalid API key")
            mock_cls.side_effect = [classifier_client, answer_client]

            with pytest.raises(PermanentError, match="Invalid API key"):
                try_answer_from_analysis(
                    question="What does this do?",
                    analysis_context="Some analysis",
                    model="test-model",
                    api_key="bad-key",
                )


class TestQueryWithShortcut:
    """Tests for query_with_shortcut() — domain-level shortcut-or-query."""

    def _make_project(self) -> MagicMock:
        project = MagicMock()
        project.query.return_value = QueryResult(
            answer="Full RLM answer",
            trace=Trace(),
            token_usage=TokenUsage(),
            execution_time=1.0,
        )
        return project

    def test_returns_shortcut_result_when_shortcut_succeeds(self):
        """When analysis can answer, returns ShortcutResult."""
        project = self._make_project()

        with patch(
            "shesha.analysis.shortcut.try_answer_from_analysis",
            return_value=("shortcut answer", 10, 5),
        ):
            result = query_with_shortcut(
                project=project,
                question="What does this do?",
                analysis_context="Overview: ...",
                model="test-model",
                api_key="key",
            )

        assert isinstance(result, ShortcutResult)
        assert result.answer == "shortcut answer"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        project.query.assert_not_called()

    def test_falls_back_to_full_query_when_shortcut_returns_none(self):
        """When shortcut returns None, falls back to project.query()."""
        project = self._make_project()

        with patch(
            "shesha.analysis.shortcut.try_answer_from_analysis",
            return_value=None,
        ):
            result = query_with_shortcut(
                project=project,
                question="Find bugs in executor",
                analysis_context="Overview: ...",
                model="test-model",
                api_key="key",
            )

        assert isinstance(result, QueryResult)
        assert result.answer == "Full RLM answer"
        project.query.assert_called_once()

    def test_skips_shortcut_when_no_analysis_context(self):
        """Without analysis_context, goes straight to project.query()."""
        project = self._make_project()

        with patch(
            "shesha.analysis.shortcut.try_answer_from_analysis",
        ) as mock_try:
            result = query_with_shortcut(
                project=project,
                question="What does this do?",
                analysis_context=None,
                model="test-model",
                api_key="key",
            )

        mock_try.assert_not_called()
        assert isinstance(result, QueryResult)

    def test_passes_on_progress_and_cancel_event_to_query(self):
        """on_progress and cancel_event are forwarded to project.query()."""
        project = self._make_project()
        progress = MagicMock()
        cancel = threading.Event()

        with patch(
            "shesha.analysis.shortcut.try_answer_from_analysis",
            return_value=None,
        ):
            query_with_shortcut(
                project=project,
                question="Q",
                analysis_context="ctx",
                model="m",
                api_key="k",
                on_progress=progress,
                cancel_event=cancel,
            )

        project.query.assert_called_once_with("ctx\n\nQ", on_progress=progress, cancel_event=cancel)

    def test_rlm_fallback_prepends_analysis_context_to_question(self):
        """When shortcut declines, project.query() receives the analysis
        context prepended to the question — matching pre-refactor behavior."""
        project = self._make_project()

        with patch(
            "shesha.analysis.shortcut.try_answer_from_analysis",
            return_value=None,
        ):
            query_with_shortcut(
                project=project,
                question="What does module X do?",
                analysis_context="Overview: A web framework.",
                model="test-model",
                api_key="key",
            )

        call_args = project.query.call_args
        question_sent = call_args[0][0]
        assert question_sent.startswith("Overview: A web framework.")
        assert "What does module X do?" in question_sent

    def test_rlm_fallback_without_analysis_context_passes_question_unchanged(self):
        """Without analysis context, project.query() receives the original question."""
        project = self._make_project()

        with patch(
            "shesha.analysis.shortcut.try_answer_from_analysis",
        ):
            query_with_shortcut(
                project=project,
                question="What does module X do?",
                analysis_context=None,
                model="test-model",
                api_key="key",
            )

        call_args = project.query.call_args
        question_sent = call_args[0][0]
        assert question_sent == "What does module X do?"

    def test_shortcut_result_is_dataclass(self):
        """ShortcutResult is a proper dataclass with expected fields."""
        sr = ShortcutResult(answer="a", prompt_tokens=1, completion_tokens=2)
        assert sr.answer == "a"
        assert sr.prompt_tokens == 1
        assert sr.completion_tokens == 2


class TestShortcutPromptContent:
    """Tests that the shortcut LLM prompt prevents absence-as-answer."""

    def test_contains_absence_rule(self):
        """Prompt explicitly forbids answering with 'analysis doesn't mention X'."""
        assert "Never answer by describing what the analysis lacks" in _SYSTEM_PROMPT

    def test_contains_need_deeper_for_missing_info(self):
        """Prompt lists 'analysis does not contain the information' as NEED_DEEPER case."""
        assert "The analysis does not contain the information needed to answer" in _SYSTEM_PROMPT

    def test_contains_absence_not_absence_principle(self):
        """Prompt states absence from analysis != absence from codebase."""
        assert (
            "Absence of information in the analysis does not mean absence in the codebase"
            in _SYSTEM_PROMPT
        )
