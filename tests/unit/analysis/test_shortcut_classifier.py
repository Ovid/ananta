"""Tests for analysis shortcut query classifier."""

from unittest.mock import MagicMock, patch

from shesha.analysis.shortcut import (
    _CLASSIFIER_PROMPT,
    classify_query,
    try_answer_from_analysis,
)


class TestClassifyQuery:
    """Tests for classify_query() — the pre-filter gate."""

    def test_returns_false_for_existence_check(self):
        """Existence questions like 'does X exist?' should bypass shortcut."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="Does SECURITY.md exist?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is False

    def test_returns_false_for_accuracy_verification(self):
        """Accuracy questions like 'is the README accurate?' should bypass."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="How accurate is the README?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is False

    def test_returns_false_for_user_doubt(self):
        """User doubt like 'I think it's wrong' should bypass shortcut."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="I think it's out of date.",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is False

    def test_returns_false_for_file_content_request(self):
        """Requests for file contents should bypass shortcut."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="What's in the Makefile?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is False

    def test_returns_true_for_architecture_question(self):
        """General architecture questions should allow shortcut."""
        mock_response = MagicMock()
        mock_response.content = "ANALYSIS_OK"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="What does this project do?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is True

    def test_returns_true_for_dependency_question(self):
        """Dependency questions should allow shortcut."""
        mock_response = MagicMock()
        mock_response.content = "ANALYSIS_OK"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="What external services does this use?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is True

    def test_returns_true_on_transient_exception(self):
        """Transient LLM exception -> True (graceful fallback, allow shortcut attempt)."""
        from shesha.llm.exceptions import TransientError

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.side_effect = TransientError("timeout")
            result = classify_query(
                question="What does this do?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is True

    def test_raises_permanent_error(self):
        """PermanentError (auth failure) propagates instead of being swallowed."""
        import pytest

        from shesha.llm.exceptions import PermanentError

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.side_effect = PermanentError("invalid key")
            with pytest.raises(PermanentError):
                classify_query(
                    question="What does this do?",
                    model="test-model",
                    api_key="test-key",
                )

    def test_returns_true_on_unparseable_output(self):
        """Unparseable LLM output -> True (graceful fallback)."""
        mock_response = MagicMock()
        mock_response.content = "I'm not sure how to classify this question."

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = classify_query(
                question="What does this do?",
                model="test-model",
                api_key="test-key",
            )

        assert result[0] is True

    def test_passes_question_to_llm(self):
        """The question is sent to the LLM as user content."""
        mock_response = MagicMock()
        mock_response.content = "ANALYSIS_OK"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.complete.return_value = mock_response
            classify_query(
                question="What does this project do?",
                model="test-model",
                api_key="test-key",
            )

        call_args = mock_client.complete.call_args
        messages = call_args[0][0]
        user_content = messages[0]["content"]
        assert "What does this project do?" in user_content

    def test_does_not_receive_analysis_context(self):
        """Classifier prompt should not contain analysis context."""
        mock_response = MagicMock()
        mock_response.content = "ANALYSIS_OK"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.complete.return_value = mock_response
            classify_query(
                question="What does this project do?",
                model="test-model",
                api_key="test-key",
            )

        # Check system prompt does not contain analysis markers
        constructor_args = mock_cls.call_args
        system_prompt = (
            constructor_args[1].get("system_prompt", "") or constructor_args[0][1]
            if len(constructor_args[0]) > 1
            else constructor_args[1].get("system_prompt", "")
        )
        assert "=== Codebase Analysis ===" not in system_prompt

        # Check user message does not contain analysis markers
        call_args = mock_client.complete.call_args
        messages = call_args[0][0]
        user_content = messages[0]["content"]
        assert "<untrusted_document_content>" not in user_content
        assert "_BEGIN" not in user_content

    def test_uses_same_model_as_shortcut(self):
        """Classifier should use the same model passed to it."""
        mock_response = MagicMock()
        mock_response.content = "ANALYSIS_OK"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            classify_query(
                question="What does this do?",
                model="my-special-model",
                api_key="my-key",
            )

        constructor_kwargs = mock_cls.call_args
        assert constructor_kwargs[1]["model"] == "my-special-model"
        assert constructor_kwargs[1]["api_key"] == "my-key"


class TestClassifierPromptContent:
    """Tests that the classifier prompt contains required guidance."""

    def test_contains_few_shot_examples(self):
        """Classifier prompt includes concrete examples for reliable classification."""
        # ANALYSIS_OK examples
        assert '"What does this project do?" → ANALYSIS_OK' in _CLASSIFIER_PROMPT
        assert '"What external dependencies does it use?" → ANALYSIS_OK' in _CLASSIFIER_PROMPT

        # NEED_DEEPER examples
        assert '"SECURITY.md?" → NEED_DEEPER' in _CLASSIFIER_PROMPT
        assert '"How accurate is the README?" → NEED_DEEPER' in _CLASSIFIER_PROMPT
        assert '"I think that\'s out of date" → NEED_DEEPER' in _CLASSIFIER_PROMPT

    def test_contains_terse_filename_rule(self):
        """Classifier prompt flags terse/ambiguous filename references."""
        assert "terse or ambiguous reference to a filename" in _CLASSIFIER_PROMPT

    def test_contains_when_in_doubt_bias(self):
        """Classifier prompt biases toward NEED_DEEPER when uncertain."""
        assert "When in doubt, respond NEED_DEEPER" in _CLASSIFIER_PROMPT


class TestLLMClientFactoryInjection:
    """Tests for llm_client_factory parameter in shortcut functions."""

    def test_classify_query_uses_injected_factory(self):
        """classify_query uses the provided llm_client_factory."""
        mock_response = MagicMock()
        mock_response.content = "ANALYSIS_OK"
        mock_response.prompt_tokens = 10
        mock_response.completion_tokens = 5

        mock_factory = MagicMock()
        mock_factory.return_value.complete.return_value = mock_response

        result = classify_query(
            question="What does this do?",
            model="test-model",
            api_key="test-key",
            llm_client_factory=mock_factory,
        )

        mock_factory.assert_called_once()
        assert result[0] is True

    def test_try_answer_uses_injected_factory(self):
        """try_answer_from_analysis uses the provided llm_client_factory."""
        classifier_response = MagicMock()
        classifier_response.content = "ANALYSIS_OK"
        classifier_response.prompt_tokens = 10
        classifier_response.completion_tokens = 5

        answer_response = MagicMock()
        answer_response.content = "The answer."
        answer_response.prompt_tokens = 50
        answer_response.completion_tokens = 10

        mock_factory = MagicMock()
        classifier_client = MagicMock()
        classifier_client.complete.return_value = classifier_response
        answer_client = MagicMock()
        answer_client.complete.return_value = answer_response
        mock_factory.side_effect = [classifier_client, answer_client]

        result = try_answer_from_analysis(
            question="What does this do?",
            analysis_context="Some analysis",
            model="test-model",
            api_key="test-key",
            llm_client_factory=mock_factory,
        )

        assert result is not None
        assert result[0] == "The answer."
        assert mock_factory.call_count == 2


class TestTryAnswerFromAnalysisWithClassifier:
    """Integration: classifier gates the shortcut LLM call."""

    def test_skips_shortcut_when_classifier_returns_false(self):
        """When classify_query returns False, shortcut returns None without calling shortcut LLM."""
        with patch("shesha.analysis.shortcut.classify_query", return_value=(False, 0, 0)):
            with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
                result = try_answer_from_analysis(
                    question="Does SECURITY.md exist?",
                    analysis_context="Some analysis",
                    model="test-model",
                    api_key="test-key",
                )

        # Should not have created an LLMClient for the shortcut
        mock_cls.assert_not_called()
        assert result is None

    def test_proceeds_with_shortcut_when_classifier_returns_true(self):
        """When classify_query returns True, shortcut proceeds normally."""
        mock_response = MagicMock()
        mock_response.content = "This project does X."
        mock_response.prompt_tokens = 50
        mock_response.completion_tokens = 10

        with patch("shesha.analysis.shortcut.classify_query", return_value=(True, 0, 0)):
            with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
                mock_cls.return_value.complete.return_value = mock_response
                result = try_answer_from_analysis(
                    question="What does this project do?",
                    analysis_context="Some analysis",
                    model="test-model",
                    api_key="test-key",
                )

        assert result == ("This project does X.", 50, 10)

    def test_shortcut_includes_classifier_tokens_in_totals(self):
        """Returned token counts include both classifier and answer LLM calls."""
        classifier_response = MagicMock()
        classifier_response.content = "ANALYSIS_OK"
        classifier_response.prompt_tokens = 30
        classifier_response.completion_tokens = 5

        answer_response = MagicMock()
        answer_response.content = "This project does X."
        answer_response.prompt_tokens = 50
        answer_response.completion_tokens = 10

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            # First LLMClient instance = classifier, second = answer
            classifier_client = MagicMock()
            classifier_client.complete.return_value = classifier_response
            answer_client = MagicMock()
            answer_client.complete.return_value = answer_response
            mock_cls.side_effect = [classifier_client, answer_client]

            result = try_answer_from_analysis(
                question="What does this project do?",
                analysis_context="Some analysis",
                model="test-model",
                api_key="test-key",
            )

        assert result is not None
        answer, prompt_tokens, completion_tokens = result
        assert answer == "This project does X."
        # 30 (classifier) + 50 (answer) = 80
        assert prompt_tokens == 80
        # 5 (classifier) + 10 (answer) = 15
        assert completion_tokens == 15

    def test_no_classifier_when_analysis_context_is_none(self):
        """When analysis_context is None, skip classifier and return None immediately."""
        with patch("shesha.analysis.shortcut.classify_query") as mock_classify:
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context=None,
                model="test-model",
                api_key="test-key",
            )

        mock_classify.assert_not_called()
        assert result is None
