"""Tests for RLM engine."""

import concurrent.futures
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha.llm.client import LLMClient
from shesha.rlm.engine import QueryResult, RLMEngine, extract_code_blocks, find_final_answer
from shesha.rlm.trace import StepType, TokenUsage, Trace
from shesha.rlm.verification import Citation, VerificationResult
from shesha.sandbox.executor import ExecutionResult, SubcallContentError
from shesha.sandbox.pool import ContainerPool
from shesha.storage.filesystem import FilesystemStorage


def test_extract_code_blocks_finds_repl():
    """extract_code_blocks finds ```repl blocks."""
    text = """Here is some code:

```repl
print("hello")
```

And more text."""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert 'print("hello")' in blocks[0]


def test_extract_code_blocks_ignores_python():
    """extract_code_blocks only matches ```repl blocks, not ```python."""
    text = """```python
x = 1
```"""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 0


def test_query_result_dataclass():
    """QueryResult stores query results."""
    result = QueryResult(
        answer="The answer",
        trace=Trace(),
        token_usage=TokenUsage(100, 50),
        execution_time=1.5,
    )
    assert result.answer == "The answer"
    assert result.execution_time == 1.5


def test_query_result_verification_defaults_none():
    """QueryResult.verification defaults to None."""
    result = QueryResult(
        answer="ans",
        trace=Trace(),
        token_usage=TokenUsage(),
        execution_time=0.0,
    )
    assert result.verification is None


def test_query_result_accepts_verification():
    """QueryResult accepts optional verification param."""

    vr = VerificationResult(
        citations=[Citation(doc_id=0, found=True)],
        quotes=[],
    )
    result = QueryResult(
        answer="ans",
        trace=Trace(),
        token_usage=TokenUsage(),
        execution_time=0.0,
        verification=vr,
    )
    assert result.verification is vr
    assert result.verification.all_valid is True


def test_engine_verify_citations_defaults_true():
    """RLMEngine.verify_citations defaults to True."""
    engine = RLMEngine(model="test-model")
    assert engine.verify_citations is True


def test_engine_verify_citations_can_be_disabled():
    """RLMEngine accepts verify_citations=False."""
    engine = RLMEngine(model="test-model", verify_citations=False)
    assert engine.verify_citations is False


def test_semantic_verification_step_type_exists():
    """SEMANTIC_VERIFICATION step type exists."""
    assert StepType.SEMANTIC_VERIFICATION.value == "semantic_verification"


def test_engine_verify_defaults_false():
    """RLMEngine.verify defaults to False."""
    engine = RLMEngine(model="test-model")
    assert engine.verify is False


def test_engine_verify_can_be_enabled():
    """RLMEngine accepts verify=True."""
    engine = RLMEngine(model="test-model", verify=True)
    assert engine.verify is True


def test_engine_accepts_llm_client_factory():
    """RLMEngine accepts an llm_client_factory parameter."""
    factory = MagicMock()
    engine = RLMEngine(model="test-model", llm_client_factory=factory)
    assert engine.llm_client_factory is factory


def test_engine_defaults_llm_client_factory_to_llm_client():
    """RLMEngine defaults llm_client_factory to LLMClient."""

    engine = RLMEngine(model="test-model")
    assert engine.llm_client_factory is LLMClient


class TestSetPool:
    """Tests for RLMEngine.set_pool()."""

    def test_set_pool_assigns_pool(self):
        """set_pool() stores the pool for use during queries."""

        engine = RLMEngine(model="test-model")
        pool = MagicMock(spec=ContainerPool)
        engine.set_pool(pool)
        assert engine.pool is pool

    def test_set_pool_accepts_none_to_clear(self):
        """set_pool(None) clears the pool, reverting to standalone executors."""

        pool = MagicMock(spec=ContainerPool)
        engine = RLMEngine(model="test-model", pool=pool)
        engine.set_pool(None)
        assert engine.pool is None


@patch("shesha.rlm.engine.ContainerExecutor")
def test_engine_uses_injected_llm_factory(mock_executor_cls: MagicMock):
    """Engine uses the injected factory instead of importing LLMClient directly."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(
        content='```repl\nFINAL("result")\n```',
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    factory = MagicMock(return_value=mock_llm)

    mock_executor = MagicMock()
    mock_executor.execute.return_value = MagicMock(
        status="ok",
        stdout="",
        stderr="",
        error=None,
        final_answer="result",
    )
    mock_executor_cls.return_value = mock_executor

    engine = RLMEngine(model="test-model", llm_client_factory=factory)
    result = engine.query(
        documents=["doc content"],
        question="What?",
    )

    assert result.answer == "result"
    factory.assert_called()


class TestRLMEngine:
    """Tests for RLMEngine."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_runs_until_final(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine runs until FINAL is called."""
        # Mock LLM to return code with FINAL
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("The answer is 42")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="The answer is 42",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        result = engine.query(
            documents=["Doc 1 content", "Doc 2 content"],
            question="What is the answer?",
        )

        assert result.answer == "The answer is 42"
        assert len(result.trace.steps) > 0

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_context_type_is_list_for_single_document(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Context metadata says 'list' even with one document (sandbox uses list)."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="done",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        engine.query(documents=["Single document content"], question="Q?")

        # Find the assistant message with context metadata
        messages = mock_llm.complete.call_args.kwargs["messages"]
        metadata_msgs = [
            m
            for m in messages
            if m.get("role") == "assistant" and "context" in m.get("content", "").lower()
        ]
        assert len(metadata_msgs) == 1
        assert "list" in metadata_msgs[0]["content"]
        assert "string" not in metadata_msgs[0]["content"]

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_honors_falsy_final_answer(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """FINAL(0), FINAL(''), FINAL(False) must terminate the loop."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL(0)\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=0,  # falsy but legitimate
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["doc"],
            question="What is zero?",
        )

        # Must detect the final answer, not iterate to max
        assert result.answer == "0"
        # LLM should only be called once (not 5 times to max iterations)
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_calls_on_progress_callback(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine calls on_progress callback for each step."""
        # Mock LLM to return code with FINAL
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="output",
            stderr="",
            error=None,
            final_answer="Done",
        )
        mock_executor_cls.return_value = mock_executor

        # Track callback invocations
        progress_calls: list[tuple[StepType, int]] = []

        def on_progress(
            step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
        ) -> None:
            progress_calls.append((step_type, iteration))

        engine = RLMEngine(model="test-model")
        result = engine.query(
            documents=["Doc content"],
            question="Test?",
            on_progress=on_progress,
        )

        assert result.answer == "Done"
        # Should have at least CODE_GENERATED, CODE_OUTPUT, FINAL_ANSWER
        step_types = [call[0] for call in progress_calls]
        assert StepType.CODE_GENERATED in step_types
        assert StepType.CODE_OUTPUT in step_types
        assert StepType.FINAL_ANSWER in step_types

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_on_progress_receives_token_usage_snapshot(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """on_progress callback receives a TokenUsage snapshot with cumulative tokens."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="output",
            stderr="",
            error=None,
            final_answer="Done",
        )
        mock_executor_cls.return_value = mock_executor

        # Track TokenUsage received in callbacks
        received_usages: list[TokenUsage] = []

        def on_progress(
            step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
        ) -> None:
            received_usages.append(token_usage)

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["Doc content"],
            question="Test?",
            on_progress=on_progress,
        )

        # Every callback should have received a TokenUsage
        assert len(received_usages) > 0
        # The last callback should reflect the accumulated tokens
        last = received_usages[-1]
        assert last.prompt_tokens >= 100
        assert last.completion_tokens >= 50

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_on_progress_token_usage_is_snapshot_not_reference(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """TokenUsage passed to on_progress is a copy, not a mutable reference."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="output",
            stderr="",
            error=None,
            final_answer="Done",
        )
        mock_executor_cls.return_value = mock_executor

        received_usages: list[TokenUsage] = []

        def on_progress(
            step_type: StepType, iteration: int, content: str, token_usage: TokenUsage
        ) -> None:
            received_usages.append(token_usage)

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["Doc content"],
            question="Test?",
            on_progress=on_progress,
        )

        # All received TokenUsage objects should be distinct instances
        ids = [id(u) for u in received_usages]
        assert len(set(ids)) == len(ids), "TokenUsage objects should be copies, not same reference"

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_acquires_executor_from_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When pool is provided, engine acquires executor from pool instead of creating one."""

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_pool = MagicMock(spec=ContainerPool)
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "answer"
        mock_pool.acquire.assert_called_once()
        mock_pool.release.assert_called_once_with(mock_executor)
        mock_executor.stop.assert_not_called()

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_resets_namespace_before_release(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine resets executor namespace before releasing back to pool."""

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("done")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_pool = MagicMock(spec=ContainerPool)
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="done",
        )
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        engine.query(documents=["doc"], question="Q?")

        mock_executor.reset_namespace.assert_called_once()

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_creates_executor_without_pool(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Without pool, engine creates and stops its own executor (backward compat)."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")  # No pool
        result = engine.query(documents=["doc"], question="Q?")

        assert result.answer == "answer"
        mock_executor_cls.assert_called_once()
        mock_executor.start.assert_called_once()
        mock_executor.stop.assert_called_once()

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_raises_for_oversized_subcall_content(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine raises SubcallContentError when subcall content exceeds limit."""

        # Create engine with small limit for testing
        engine = RLMEngine(model="test-model", max_subcall_content_chars=1000)

        # Call _handle_llm_query directly with oversized content
        trace = Trace()
        token_usage = TokenUsage()
        large_content = "x" * 5000  # 5K chars, exceeds 1K limit

        with pytest.raises(SubcallContentError) as exc_info:
            engine._handle_llm_query(
                instruction="Summarize this",
                content=large_content,
                trace=trace,
                token_usage=token_usage,
                iteration=0,
                boundary="test",
            )

        error_msg = str(exc_info.value)
        # Size is instruction + content (5000 + len("Summarize this") = 5014)
        assert "5,014" in error_msg or "5014" in error_msg  # actual size
        assert "1,000" in error_msg or "1000" in error_msg  # limit
        assert "chunk" in error_msg.lower()  # guidance to chunk smaller
        mock_llm_cls.assert_not_called()  # No sub-LLM call made

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_allows_subcall_content_under_limit(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Engine makes sub-LLM call when content is under limit."""
        # Mock sub-LLM
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content="Analysis result",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
        )
        mock_llm_cls.return_value = mock_sub_llm

        # Create engine with reasonable limit
        engine = RLMEngine(model="test-model", max_subcall_content_chars=10000)

        trace = Trace()
        token_usage = TokenUsage()
        small_content = "x" * 500  # 500 chars, under 10K limit

        result = engine._handle_llm_query(
            instruction="Summarize this",
            content=small_content,
            trace=trace,
            token_usage=token_usage,
            iteration=0,
            boundary="test",
        )

        # Should return LLM response
        assert result == "Analysis result"
        mock_llm_cls.assert_called_once()  # Sub-LLM was called

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_raises_for_oversized_instruction_when_content_empty(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Size limit applies to instruction when content is empty (single-arg form)."""

        engine = RLMEngine(model="test-model", max_subcall_content_chars=1000)
        trace = Trace()
        token_usage = TokenUsage()
        large_instruction = "x" * 5000  # 5K chars, exceeds 1K limit

        with pytest.raises(SubcallContentError):
            engine._handle_llm_query(
                instruction=large_instruction,
                content="",
                trace=trace,
                token_usage=token_usage,
                iteration=0,
                boundary="test",
            )

        mock_llm_cls.assert_not_called()

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_skips_wrapping_when_content_empty(
        self,
        mock_llm_cls: MagicMock,
    ):
        """_handle_llm_query sends instruction directly when content is empty."""
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content="Result",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
        )
        mock_llm_cls.return_value = mock_sub_llm

        engine = RLMEngine(model="test-model", max_subcall_content_chars=10000)
        trace = Trace()
        token_usage = TokenUsage()

        engine._handle_llm_query(
            instruction="What is 2+2?",
            content="",
            trace=trace,
            token_usage=token_usage,
            iteration=0,
            boundary="test",
        )

        # Verify the prompt sent does NOT contain untrusted wrapping tags
        call_args = mock_sub_llm.complete.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        prompt_text = messages[0]["content"]
        assert "_BEGIN" not in prompt_text
        assert "What is 2+2?" in prompt_text

    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_wraps_subcall_content_in_untrusted_tags(
        self,
        mock_llm_cls: MagicMock,
    ):
        """_handle_llm_query wraps content in untrusted tags before calling LLM."""
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content="Summary result",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
        )
        mock_llm_cls.return_value = mock_sub_llm

        engine = RLMEngine(model="test-model", max_subcall_content_chars=10000)
        trace = Trace()
        token_usage = TokenUsage()

        engine._handle_llm_query(
            instruction="Summarize this",
            content="Untrusted document data",
            trace=trace,
            token_usage=token_usage,
            iteration=0,
            boundary="test",
        )

        # Verify the prompt sent to LLM contains the wrapping tags
        call_args = mock_sub_llm.complete.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        prompt_text = messages[0]["content"]
        assert "_BEGIN" in prompt_text
        assert "_END" in prompt_text
        assert "Untrusted document data" in prompt_text

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_runs_semantic_verification_when_enabled(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Engine runs semantic verification when verify=True."""
        verification_findings = json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "P0.1",
                        "original_claim": "Issue",
                        "confidence": "high",
                        "reason": "Confirmed.",
                        "evidence_classification": "code_analysis",
                        "flags": [],
                    }
                ]
            }
        )

        # Mock LLM: first call is the main query, subsequent calls are verification subcalls.
        # doc_names=["main.py"] is a code file, so Layer 2 also runs (3 LLM calls total).
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Main query response
            MagicMock(
                content='```repl\nFINAL("## P0.1: Issue\\nSee Doc 0.")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Layer 1: Adversarial verification subcall response
            MagicMock(
                content=verification_findings,
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
            # Layer 2: Code-specific verification subcall response
            MagicMock(
                content=verification_findings,
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        verification_json = json.dumps(
            {
                "citations": [{"doc_id": 0, "found": True}],
                "quotes": [],
            }
        )
        mock_executor.execute.side_effect = [
            # FINAL execution
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="## P0.1: Issue\nSee Doc 0.",
            ),
            # Mechanical verification
            MagicMock(
                status="ok",
                stdout=verification_json,
                stderr="",
                error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=True)
        result = engine.query(
            documents=["Doc content here"],
            question="Find issues",
            doc_names=["main.py"],
        )

        assert result.semantic_verification is not None
        assert len(result.semantic_verification.findings) == 1
        assert result.semantic_verification.findings[0].confidence == "high"

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_skips_semantic_verification_when_disabled(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Engine skips semantic verification when verify=False."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=False, verify_citations=False)
        result = engine.query(documents=["Doc"], question="What?")

        assert result.semantic_verification is None

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_semantic_verification_failure_does_not_block_answer(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Semantic verification failure doesn't prevent answer delivery."""
        # Answer must reference Doc 0 so gather_cited_documents finds citations
        final_answer_text = "See Doc 0 for details"
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content=f'```repl\nFINAL("{final_answer_text}")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Verification subcall returns garbage (unparseable)
            MagicMock(
                content="I refuse to output JSON",
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=final_answer_text,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=False)
        result = engine.query(
            documents=["Doc content"],
            question="What?",
            doc_names=["file.txt"],
        )

        assert result.answer == final_answer_text
        assert result.semantic_verification is None
        # Error recorded in trace
        sem_steps = [s for s in result.trace.steps if s.type == StepType.SEMANTIC_VERIFICATION]
        assert len(sem_steps) >= 1
        last_step = sem_steps[-1].content
        assert "error" in last_step.lower() or "Could not parse" in last_step

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_semantic_verification_wraps_documents_in_untrusted_tags(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Verification prompts wrap cited documents in untrusted content tags."""
        verification_findings = json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "F1",
                        "original_claim": "Claim",
                        "confidence": "high",
                        "reason": "Confirmed.",
                        "evidence_classification": "code_analysis",
                        "flags": [],
                    }
                ]
            }
        )

        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Main query
            MagicMock(
                content='```repl\nFINAL("## F1: Claim\\nSee Doc 0.")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Layer 1 verification
            MagicMock(
                content=verification_findings,
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="## F1: Claim\nSee Doc 0.",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify=True, verify_citations=False)
        engine.query(
            documents=["Untrusted doc content here"],
            question="Analyze",
            doc_names=["notes.txt"],
        )

        # Layer 1 verification is the 2nd LLM call (index 1)
        layer1_call = mock_llm.complete.call_args_list[1]
        layer1_prompt = layer1_call.kwargs["messages"][0]["content"]
        assert "_BEGIN" in layer1_prompt
        assert "_END" in layer1_prompt

    @patch("shesha.rlm.engine.LLMClient")
    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_semantic_verification_skips_when_cited_docs_exceed_size_limit(
        self,
        mock_executor_cls: MagicMock,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Verification is skipped when cited documents exceed size limit."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Main query
            MagicMock(
                content='```repl\nFINAL("See Doc 0.")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="See Doc 0.",
        )
        mock_executor_cls.return_value = mock_executor

        # Set a very small content limit
        engine = RLMEngine(
            model="test-model",
            verify=True,
            verify_citations=False,
            max_subcall_content_chars=10,
        )
        result = engine.query(
            documents=["A" * 100],
            question="Analyze",
            doc_names=["big.txt"],
        )

        # Verification should be skipped (not errored)
        assert result.semantic_verification is None
        # Only 1 LLM call (main query), no verification calls
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_handles_final_var(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine handles FINAL_VAR by using final_value from executor."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL_VAR("my_answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=None,
            final_var="my_answer",
            final_value="The computed answer",
            vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        result = engine.query(
            documents=["Doc content"],
            question="What is the answer?",
        )

        assert result.answer == "The computed answer"

    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_engine_retries_when_code_block_final_var_value_is_none(
        self,
        mock_executor_cls: MagicMock,
    ):
        """When executor returns final_var with final_value=None, engine retries
        via _resolve_final_var rather than returning an empty answer."""
        mock_llm = MagicMock()
        # First call: model writes FINAL_VAR in code block
        # Second call: model writes FINAL with literal answer after retry
        mock_llm.complete.side_effect = [
            MagicMock(
                content='```repl\nFINAL_VAR("missing_var")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content='```repl\nFINAL("fallback answer")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_factory = MagicMock(return_value=mock_llm)

        mock_executor = MagicMock()
        # First execute: FINAL_VAR code block — var not found
        # (final_var set but final_value is None)
        exec_result_1 = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=None,
            final_var="missing_var",
            final_value=None,
            vars=None,
        )
        # _resolve_final_var calls execute(print(missing_var)) — fails
        resolve_result = MagicMock(
            status="error",
            stdout="",
            stderr="NameError: name 'missing_var' is not defined",
            error="NameError",
        )
        # Second execute: FINAL with literal
        exec_result_2 = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="fallback answer",
            final_var=None,
            final_value=None,
            vars=None,
        )
        # Post-loop re-resolution also fails (var still undefined after
        # single code block), then outer loop retries with guidance.
        resolve_result_2 = MagicMock(
            status="error",
            stdout="",
            stderr="NameError: name 'missing_var' is not defined",
            error="NameError",
        )
        mock_executor.execute.side_effect = [
            exec_result_1,
            resolve_result,
            resolve_result_2,
            exec_result_2,
        ]
        mock_executor.is_alive = True
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", llm_client_factory=mock_factory)
        result = engine.query(
            documents=["Doc content"],
            question="What?",
        )

        # Should NOT be empty — should have retried and got "fallback answer"
        assert result.answer == "fallback answer"
        assert result.answer != ""


class TestCodeBlockFinalVarRetryGuidance:
    """Tests for retry guidance when FINAL_VAR fails in code block."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_code_block_final_var_failure_sends_retry_guidance(
        self,
        mock_executor_cls: MagicMock,
    ):
        """When code-block FINAL_VAR fails, engine sends 'variable not found'
        guidance to the model, matching the bare-text FINAL_VAR retry path."""
        mock_llm = MagicMock()
        # First call: code block with FINAL_VAR that fails
        # Second call: model retries successfully
        mock_llm.complete.side_effect = [
            MagicMock(
                content='```repl\nFINAL_VAR("missing_var")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content='```repl\nFINAL("correct answer")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_factory = MagicMock(return_value=mock_llm)

        mock_executor = MagicMock()
        # First: code block with FINAL_VAR — var not found
        exec_result_1 = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=None,
            final_var="missing_var",
            final_value=None,
            vars=None,
        )
        # _resolve_final_var attempt — fails
        resolve_result = MagicMock(
            status="error",
            stdout="",
            stderr="NameError: name 'missing_var' is not defined",
            error="NameError",
        )
        # Second iteration: FINAL with literal
        exec_result_2 = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="correct answer",
            final_var=None,
            final_value=None,
            vars=None,
        )
        # Post-loop re-resolution also fails (var still undefined)
        resolve_result_2 = MagicMock(
            status="error",
            stdout="",
            stderr="NameError: name 'missing_var' is not defined",
            error="NameError",
        )
        mock_executor.execute.side_effect = [
            exec_result_1,
            resolve_result,
            resolve_result_2,
            exec_result_2,
        ]
        mock_executor.is_alive = True
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", llm_client_factory=mock_factory)
        engine.query(documents=["Doc content"], question="What?")

        # Check the messages sent in the second LLM call
        second_call_messages = mock_llm.complete.call_args_list[1].kwargs["messages"]
        guidance_msgs = [
            msg
            for msg in second_call_messages
            if msg.get("role") == "user" and "was not found" in msg.get("content", "")
        ]
        assert len(guidance_msgs) == 1, "Expected retry guidance message for failed FINAL_VAR"
        assert "missing_var" in guidance_msgs[0]["content"]
        assert "Define it in a ```repl``` block" in guidance_msgs[0]["content"]


class TestIterationQueryReminder:
    """Tests for query reminder appended to iteration messages."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_iteration_message_contains_query_reminder(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """After iteration 0, user messages should contain the original query."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Iteration 0: code with no FINAL
            MagicMock(
                content='```repl\nprint("exploring")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Iteration 1: code with FINAL
            MagicMock(
                content='```repl\nFINAL("done")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # Iteration 0: no FINAL
            MagicMock(
                status="ok",
                stdout="exploring\n",
                stderr="",
                error=None,
                final_answer=None,
                final_var=None,
                vars=None,
            ),
            # Iteration 1: FINAL
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="done",
                final_var=None,
                vars=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["test doc"],
            question="What color is the sky?",
        )

        # Check the messages sent on the second LLM call (iteration 1)
        second_call_args = mock_llm.complete.call_args_list[1]
        messages = second_call_args[1].get(
            "messages", second_call_args[0][0] if second_call_args[0] else None
        )
        user_messages = [m for m in messages if m["role"] == "user"]

        # Last user message is the continuation prompt with the original query
        continuation_msg = user_messages[-1]["content"]
        assert "What color is the sky?" in continuation_msg

        # Second-to-last user message is the code echo with REPL output
        code_echo_msg = user_messages[-2]["content"]
        assert "REPL output:" in code_echo_msg
        assert "Code executed:" in code_echo_msg


class TestCallbackIterationCapture:
    """Tests for llm_query_callback capturing the correct iteration."""

    @patch("shesha.rlm.engine.LLMClient")
    def test_callback_captures_iteration_at_creation_time(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """llm_query callback uses the iteration it was created for, not a stale value.

        Bug: callback captured `current_iteration` by reference, so by the time
        it was called, the value could have advanced to a later iteration.
        """

        captured_iterations: list[int] = []

        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Iteration 0: code with no FINAL
            MagicMock(
                content='```repl\nprint("hello")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Iteration 1: code with FINAL
            MagicMock(
                content='```repl\nFINAL("done")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        exec_count = [0]

        def mock_execute(code, timeout=30):
            exec_count[0] += 1
            if exec_count[0] == 1:
                # Iteration 0: trigger llm_query callback during execute
                handler = mock_executor.llm_query_handler
                if handler and callable(handler):
                    handler("summarize", "data")
                return MagicMock(
                    status="ok",
                    stdout="hello",
                    stderr="",
                    error=None,
                    final_answer=None,
                    final_var=None,
                    vars=None,
                )
            return MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="done",
                final_var=None,
                vars=None,
            )

        mock_executor.execute.side_effect = mock_execute

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)

        def capturing_handle(inst, cont, trace, tu, iteration, *a, **kw):
            captured_iterations.append(iteration)
            return "summary"

        engine._handle_llm_query = capturing_handle

        engine.query(documents=["Doc content"], question="What?")

        # The callback was triggered during iteration 0's execute.
        # It should pass iteration=0 to _handle_llm_query.
        assert len(captured_iterations) == 1
        assert captured_iterations[0] == 0, (
            f"Callback during iteration 0 should pass iteration=0, got {captured_iterations[0]}"
        )

    @patch("shesha.rlm.engine.LLMClient")
    def test_recovery_callback_uses_current_iteration(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """After dead executor recovery, the new callback uses the current iteration."""

        captured_iterations: list[int] = []

        mock_llm = MagicMock()
        call_count = [0]

        def llm_side_effect(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(
                    content='```repl\nprint("boom")\n```',
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                )
            return MagicMock(
                content='```repl\nFINAL("recovered")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )

        mock_llm.complete.side_effect = llm_side_effect
        mock_llm_cls.return_value = mock_llm

        # First executor: dies on execute
        dead_executor = MagicMock()
        dead_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            dead_executor.is_alive = False
            return ExecutionResult(
                status="error", stdout="", stderr="", return_value=None, error="Protocol error"
            )

        dead_executor.execute.side_effect = kill_on_execute

        # Second executor: works, triggers callback during execute
        fresh_executor = MagicMock()
        fresh_executor.is_alive = True

        def fresh_execute(code, timeout=30):
            handler = fresh_executor.llm_query_handler
            if handler and callable(handler):
                handler("x", "y")
            return MagicMock(
                status="ok", stdout="", stderr="", error=None, final_answer="recovered"
            )

        fresh_executor.execute.side_effect = fresh_execute

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.acquire.side_effect = [dead_executor, fresh_executor]

        engine = RLMEngine(model="test-model", pool=mock_pool, verify_citations=False)

        def capturing_handle(inst, cont, trace, tu, iteration, *a, **kw):
            captured_iterations.append(iteration)
            return "recovered"

        engine._handle_llm_query = capturing_handle

        engine.query(documents=["doc"], question="Q?")

        # Should be iteration 1 (the iteration where recovery happened)
        assert len(captured_iterations) == 1
        assert captured_iterations[0] == 1


class TestDeadExecutorNoPool:
    """Tests for early exit when executor dies without pool."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_only_one_llm_call_when_executor_dies(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine makes only 1 LLM call, not 20, when executor dies without pool."""

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nprint("big output")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            mock_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error: line too long",
            )

        mock_executor.execute.side_effect = kill_on_execute
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=20)  # No pool
        engine.query(documents=["doc"], question="Q?")

        # Should have only called LLM once, not continued for 20 iterations
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_executor_died_answer_distinct_from_max_iterations(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Early exit answer is distinct from max iterations message."""

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nprint("boom")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            mock_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error: overflow",
            )

        mock_executor.execute.side_effect = kill_on_execute
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")  # No pool
        result = engine.query(documents=["doc"], question="Q?")

        # Answer should mention executor dying, not "max iterations"
        assert "max iterations" not in result.answer.lower()
        assert "executor" in result.answer.lower() or "died" in result.answer.lower()


class TestDeadExecutorWithPool:
    """Tests for dead executor recovery when pool is available."""

    @patch("shesha.rlm.engine.LLMClient")
    def test_dead_executor_stopped_before_discard(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """Dead executor is stopped before being discarded from pool."""

        mock_llm = MagicMock()
        call_count = 0

        def llm_side_effect(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    content='```repl\nprint("boom")\n```',
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                )
            return MagicMock(
                content='```repl\nFINAL("recovered")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )

        mock_llm.complete.side_effect = llm_side_effect
        mock_llm_cls.return_value = mock_llm

        # First executor: dies on execute
        dead_executor = MagicMock()
        dead_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            dead_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error",
            )

        dead_executor.execute.side_effect = kill_on_execute

        # Second executor: works fine
        fresh_executor = MagicMock()
        fresh_executor.is_alive = True
        fresh_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="recovered",
        )

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.acquire.side_effect = [dead_executor, fresh_executor]

        engine = RLMEngine(model="test-model", pool=mock_pool)
        result = engine.query(documents=["doc"], question="Q?")

        assert result.answer == "recovered"
        dead_executor.stop.assert_called_once()
        mock_pool.discard.assert_called_once_with(dead_executor)


class TestDeadExecutorPoolStopped:
    """Test that pool.acquire() RuntimeError during recovery is handled gracefully."""

    @patch("shesha.rlm.engine.LLMClient")
    def test_pool_acquire_raises_runtime_error_aborts_gracefully(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """If pool.acquire() raises RuntimeError (pool stopped), abort gracefully."""

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nprint("boom")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        dead_executor = MagicMock()
        dead_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            dead_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error",
            )

        dead_executor.execute.side_effect = kill_on_execute

        mock_pool = MagicMock(spec=ContainerPool)
        # First acquire returns the dead executor; recovery acquire raises
        mock_pool.acquire.side_effect = [
            dead_executor,
            RuntimeError("Cannot acquire from a stopped pool"),
        ]

        engine = RLMEngine(model="test-model", pool=mock_pool)
        result = engine.query(documents=["doc"], question="Q?")

        # Should abort gracefully, not propagate RuntimeError
        assert "died" in result.answer.lower() or "executor" in result.answer.lower()


class TestPostLoopFinalVarRetryTrace:
    """Tests for trace/callback emission on post-loop FINAL_VAR retry."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_post_loop_retry_emits_trace_step_and_progress(self, mock_executor_cls: MagicMock):
        """When a FINAL_VAR fails initially but is resolved in the post-loop
        retry, a FINAL_ANSWER trace step and on_progress callback must be emitted."""
        mock_llm = MagicMock()
        # Response contains code block with FINAL_VAR, plus a second block
        # that defines the variable.
        mock_llm.complete.side_effect = [
            MagicMock(
                content=('```repl\nFINAL_VAR("result")\n```\n\n```repl\nresult = "found it"\n```'),
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]

        mock_executor = MagicMock()
        # First execute: FINAL_VAR("result") — var not found yet
        exec_result_1 = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=None,
            final_var="result",
            final_value=None,
            vars=None,
        )
        # In-block _resolve_final_var — fails
        resolve_fail = MagicMock(
            status="error",
            stdout="",
            stderr="NameError",
            error="NameError",
        )
        # Second execute: defines variable
        exec_result_2 = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer=None,
            final_var=None,
            final_value=None,
            vars=None,
        )
        # Post-loop _resolve_final_var — succeeds
        resolve_ok = MagicMock(status="ok", stdout="found it\n")

        mock_executor.execute.side_effect = [
            exec_result_1,
            resolve_fail,
            exec_result_2,
            resolve_ok,
        ]
        mock_executor.is_alive = True
        mock_executor_cls.return_value = mock_executor

        on_progress = MagicMock()
        engine = RLMEngine(model="test-model", llm_client_factory=MagicMock(return_value=mock_llm))
        result = engine.query(
            documents=["Doc content"],
            question="What?",
            on_progress=on_progress,
        )

        assert result.answer == "found it"
        # Trace should have a FINAL_ANSWER step with post_loop_var_retry source
        final_steps = [s for s in result.trace.steps if s.type == StepType.FINAL_ANSWER]
        assert len(final_steps) == 1
        assert final_steps[0].metadata.get("source") == "post_loop_var_retry"
        # on_progress should have been called with FINAL_ANSWER
        progress_calls = [c for c in on_progress.call_args_list if c[0][0] == StepType.FINAL_ANSWER]
        assert len(progress_calls) == 1


class TestResolveFinalVar:
    """Tests for _resolve_final_var edge cases."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_empty_string_is_valid_answer(self, mock_executor_cls: MagicMock):
        """A variable holding an empty string is a valid answer, not None."""
        engine = RLMEngine(model="test-model", llm_client_factory=MagicMock())
        mock_executor = MagicMock()
        # print(var) returns empty string
        mock_executor.execute.return_value = MagicMock(status="ok", stdout="")

        result = engine._resolve_final_var("my_var", mock_executor)
        # Empty string should be returned as a valid value, not None
        assert result is not None
        assert result == ""

    @patch("shesha.rlm.engine.ContainerExecutor")
    def test_none_variable_returns_none(self, mock_executor_cls: MagicMock):
        """S1: print(None) outputs 'None' — must return None, not the string."""
        engine = RLMEngine(model="test-model", llm_client_factory=MagicMock())
        mock_executor = MagicMock()
        # print(None) in Python outputs "None\n"
        mock_executor.execute.return_value = MagicMock(status="ok", stdout="None\n")

        result = engine._resolve_final_var("my_var", mock_executor)
        assert result is None

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_bare_final_var_empty_string_accepted_without_code_blocks(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """I1: bare FINAL_VAR resolving to '' must be accepted, not retried."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="FINAL_VAR(my_var)",
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        # _resolve_final_var prints the var and gets ""
        mock_executor.execute.return_value = MagicMock(status="ok", stdout="")
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        result = engine.query(documents=["Doc"], question="What?")

        assert result.answer == ""
        # Should be one LLM call only (no retry)
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_bare_final_var_empty_string_accepted_after_code_blocks(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """I1: bare FINAL_VAR after code blocks resolving to '' accepted."""
        mock_llm = MagicMock()
        # Response has both a code block and a bare FINAL_VAR
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nmy_var = ""\n```\nFINAL_VAR(my_var)',
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        # Code block execution: no final answer
        mock_executor.execute.side_effect = [
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer=None,
                final_var=None,
                final_value=None,
                vars=None,
            ),
            # _resolve_final_var for the bare FINAL_VAR
            MagicMock(status="ok", stdout=""),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        result = engine.query(documents=["Doc"], question="What?")

        assert result.answer == ""
        assert mock_llm.complete.call_count == 1


class TestEngineTraceWriterSuppression:
    """Tests for engine trace writer suppress_errors configuration."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_creates_incremental_trace_writer_with_suppress_errors(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Engine creates IncrementalTraceWriter with suppress_errors=True."""

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        with patch("shesha.rlm.engine.IncrementalTraceWriter") as mock_inc_writer_cls:
            mock_inc_writer = MagicMock()
            mock_inc_writer.path = None
            mock_inc_writer_cls.return_value = mock_inc_writer

            engine = RLMEngine(model="test-model")
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )

            mock_inc_writer_cls.assert_called_once_with(storage, suppress_errors=True)

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_creates_trace_writer_with_suppress_errors(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Engine creates TraceWriter with suppress_errors=True for cleanup."""

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        with patch("shesha.rlm.engine.TraceWriter") as mock_writer_cls:
            mock_writer = MagicMock()
            mock_writer_cls.return_value = mock_writer

            engine = RLMEngine(model="test-model")
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )

            mock_writer_cls.assert_called_once_with(storage, suppress_errors=True)


class TestEngineTraceWriting:
    """Tests for trace writing integration."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_writes_trace_when_storage_provided(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Query writes trace file when storage is provided."""

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        # Configure mock to return FINAL answer
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["doc content"],
            question="What?",
            storage=storage,
            project_id="test-project",
        )

        traces = storage.list_traces("test-project")
        assert len(traces) == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_writes_trace_incrementally(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Query writes trace steps incrementally, not just at the end."""

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('done')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="done",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        engine.query(
            documents=["doc content"],
            question="What?",
            storage=storage,
            project_id="test-project",
        )

        traces = storage.list_traces("test-project")
        assert len(traces) == 1

        # Verify JSONL has header, steps, and summary
        lines = traces[0].read_text().strip().split("\n")
        assert len(lines) >= 3  # header + at least one step + summary

        header = json.loads(lines[0])
        assert header["type"] == "header"
        assert header["question"] == "What?"

        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["status"] == "success"

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_writes_partial_trace_on_exception(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """If query is interrupted by exception, partial trace is still written."""

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        # LLM returns code, then raises on second call
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content="```repl\nprint('hello')\n```",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            KeyboardInterrupt(),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="hello",
            stderr="",
            error=None,
            final_answer=None,  # No final answer, loop continues
            final_var=None,
            vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        try:
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )
        except KeyboardInterrupt:
            pass  # Expected

        # Partial trace should still exist
        traces = storage.list_traces("test-project")
        assert len(traces) == 1

        lines = traces[0].read_text().strip().split("\n")

        # Should have header
        header = json.loads(lines[0])
        assert header["type"] == "header"

        # Should have at least the steps from iteration 0
        step_lines = [json.loads(line) for line in lines[1:] if json.loads(line)["type"] == "step"]
        assert len(step_lines) >= 1

        # Should have summary with interrupted status
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["status"] == "interrupted"


class TestEngineMaxTracesConfig:
    """Tests for max_traces_per_project plumbing."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_passes_max_traces_to_cleanup(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Engine passes max_traces_per_project to cleanup_old_traces."""

        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        with patch("shesha.rlm.engine.TraceWriter") as mock_writer_cls:
            mock_writer = MagicMock()
            mock_writer_cls.return_value = mock_writer

            engine = RLMEngine(model="test-model", max_traces_per_project=25)
            engine.query(
                documents=["doc content"],
                question="What?",
                storage=storage,
                project_id="test-project",
            )

            mock_writer.cleanup_old_traces.assert_called_once_with("test-project", max_count=25)


class TestEngineVerification:
    """Tests for post-FINAL citation verification."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_runs_verification_after_final(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Engine runs verification after FINAL and populates result.verification."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 says something")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        verification_json = json.dumps(
            {
                "citations": [{"doc_id": 0, "found": True}],
                "quotes": [],
            }
        )

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # First call: the FINAL answer execution
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 says something",
            ),
            # Second call: verification code execution
            MagicMock(
                status="ok",
                stdout=verification_json,
                stderr="",
                error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 says something"
        assert result.verification is not None
        assert len(result.verification.citations) == 1
        assert result.verification.citations[0].found is True
        assert mock_executor.execute.call_count == 2

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_skips_verification_when_disabled(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Engine skips verification when verify_citations=False."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 says something")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="Doc 0 says something",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=False)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 says something"
        assert result.verification is None
        assert mock_executor.execute.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_handles_verification_failure_gracefully(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Verification failure doesn't affect answer delivery."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # First call: FINAL answer
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 answer",
            ),
            # Second call: verification fails
            MagicMock(
                status="error",
                stdout="",
                stderr="Traceback: something broke",
                error="execution error",
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 answer"
        assert result.verification is None

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_adds_verification_trace_step(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """VERIFICATION step appears in trace after successful verification."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 says something")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        verification_json = json.dumps(
            {
                "citations": [{"doc_id": 0, "found": True}],
                "quotes": [],
            }
        )

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 says something",
            ),
            MagicMock(
                status="ok",
                stdout=verification_json,
                stderr="",
                error=None,
                final_answer=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        step_types = [s.type for s in result.trace.steps]
        assert StepType.VERIFICATION in step_types

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_records_verification_error_in_trace(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Verification exception is recorded as a VERIFICATION trace step."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("Doc 0 answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # First call: FINAL answer
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer="Doc 0 answer",
            ),
            # Second call: verification raises
            ValueError("Could not parse verification output: no valid JSON found"),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", verify_citations=True)
        result = engine.query(documents=["Doc content"], question="What?")

        assert result.answer == "Doc 0 answer"
        assert result.verification is None
        # Error should be recorded in a VERIFICATION trace step
        verification_steps = [s for s in result.trace.steps if s.type == StepType.VERIFICATION]
        assert len(verification_steps) == 1
        assert "Could not parse verification output" in verification_steps[0].content


class TestHandleLlmQueryThreadSafety:
    """Tests for thread safety of _handle_llm_query."""

    def test_handle_llm_query_is_thread_safe(self) -> None:
        """Concurrent _handle_llm_query calls must not corrupt shared state.

        When the executor dispatches batch prompts concurrently, multiple
        threads call _handle_llm_query simultaneously. Trace steps and
        token counts must be consistent.
        """

        mock_response = MagicMock(
            content="answer",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        mock_llm_factory = MagicMock()
        mock_llm_factory.return_value.complete.return_value = mock_response

        engine = RLMEngine(model="test-model", llm_client_factory=mock_llm_factory)
        trace = Trace()
        token_usage = TokenUsage()
        n_calls = 20

        def call_handler(i: int) -> str:
            return engine._handle_llm_query(
                instruction=f"prompt_{i}",
                content="",
                trace=trace,
                token_usage=token_usage,
                iteration=0,
                boundary="test",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(call_handler, range(n_calls)))

        assert len(results) == n_calls
        # Each call adds 2 steps (SUBCALL_REQUEST + SUBCALL_RESPONSE)
        assert len(trace.steps) == n_calls * 2
        # Token counts should reflect all calls
        assert token_usage.prompt_tokens == n_calls * 10
        assert token_usage.completion_tokens == n_calls * 5


class TestBoundaryNotSharedState:
    """Boundary must be per-query, not stored on the engine instance."""

    @patch("shesha.rlm.engine.LLMClient")
    def test_handle_llm_query_uses_boundary_parameter(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """_handle_llm_query wraps content using the boundary argument, not self._boundary."""
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content="result",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_llm_cls.return_value = mock_sub_llm

        engine = RLMEngine(model="test-model")
        trace = Trace()
        token_usage = TokenUsage()

        # Pass an explicit boundary that differs from any engine default
        explicit_boundary = "EXPLICIT_TEST_BOUNDARY_12345"
        engine._handle_llm_query(
            instruction="Summarize",
            content="Some document",
            trace=trace,
            token_usage=token_usage,
            iteration=0,
            boundary=explicit_boundary,
        )

        call_args = mock_sub_llm.complete.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        prompt_text = messages[0]["content"]
        assert explicit_boundary in prompt_text

    @patch("shesha.rlm.engine.LLMClient")
    def test_semantic_verification_uses_boundary_parameter(
        self,
        mock_llm_cls: MagicMock,
    ) -> None:
        """_run_semantic_verification wraps docs using the boundary argument."""
        mock_sub_llm = MagicMock()
        mock_sub_llm.complete.return_value = MagicMock(
            content='{"findings": []}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_llm_cls.return_value = mock_sub_llm

        engine = RLMEngine(model="test-model")
        trace = Trace()
        token_usage = TokenUsage()

        explicit_boundary = "SEMANTIC_BOUNDARY_99999"
        engine._run_semantic_verification(
            final_answer="The code uses pattern X in context[0]",
            documents=["def foo(): pass"],
            doc_names=["module.py"],
            trace=trace,
            token_usage=token_usage,
            iteration=0,
            boundary=explicit_boundary,
        )

        call_args = mock_sub_llm.complete.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        prompt_text = messages[0]["content"]
        assert explicit_boundary in prompt_text


class TestFindFinalAnswerInText:
    """Tests for find_final_answer detecting bare FINAL/FINAL_VAR in response text."""

    def test_find_final_answer_bare_final(self):
        """Detects bare FINAL("answer") outside code blocks, strips quotes."""

        text = 'FINAL("human being")'
        result = find_final_answer(text)
        assert result == ("final", "human being")

    def test_find_final_answer_bare_final_var(self):
        """Detects bare FINAL_VAR(var_name) outside code blocks."""

        text = "FINAL_VAR(my_answer)"
        result = find_final_answer(text)
        assert result == ("final_var", "my_answer")

    def test_find_final_answer_returns_none_for_no_match(self):
        """Returns None when no FINAL pattern is present."""

        text = "Let me continue exploring the data."
        result = find_final_answer(text)
        assert result is None

    def test_find_final_answer_ignores_inside_repl_block(self):
        """Does NOT match FINAL inside a ```repl block (handled by executor)."""

        text = '```repl\nFINAL("answer")\n```'
        result = find_final_answer(text)
        assert result is None

    def test_find_final_answer_with_leading_whitespace(self):
        """FINAL at start of line with whitespace is detected, strips quotes."""

        text = '  FINAL("the answer")'
        result = find_final_answer(text)
        assert result == ("final", "the answer")

    def test_find_final_answer_strips_quotes_from_var(self):
        """FINAL_VAR with quoted variable name strips quotes."""

        text = 'FINAL_VAR("my_var")'
        result = find_final_answer(text)
        assert result == ("final_var", "my_var")

    def test_find_final_var_non_identifier_treated_as_literal(self):
        """FINAL_VAR with non-identifier content falls back to literal."""

        # Dotted expression — not a valid identifier, must not become final_var
        result = find_final_answer("FINAL_VAR(foo.bar)")
        assert result == ("final", "foo.bar")

    def test_find_final_var_expression_treated_as_literal(self):
        """FINAL_VAR(x + y) with operators falls back to literal."""

        result = find_final_answer("FINAL_VAR(x + y)")
        assert result == ("final", "x + y")

    def test_find_final_var_keyword_treated_as_literal(self):
        """FINAL_VAR(True) with Python keyword falls back to literal."""

        result = find_final_answer("FINAL_VAR(True)")
        assert result == ("final", "True")

    def test_find_final_var_valid_identifier_still_works(self):
        """FINAL_VAR(valid_name) with a valid identifier stays as final_var."""

        result = find_final_answer("FINAL_VAR(my_answer)")
        assert result == ("final_var", "my_answer")

    def test_find_final_answer_unquoted_content(self):
        """FINAL(bare text) without quotes is detected (reference RLM compat)."""

        result = find_final_answer("FINAL(42)")
        assert result == ("final", "42")

    def test_find_final_answer_single_quoted_content(self):
        """FINAL('single quoted') strips quotes (reference RLM compat)."""

        result = find_final_answer("FINAL('hello world')")
        assert result == ("final", "hello world")

    def test_find_final_answer_nested_parentheses(self):
        """FINAL with nested parens uses greedy match (reference RLM compat)."""

        result = find_final_answer("FINAL(func(arg1, arg2))")
        assert result == ("final", "func(arg1, arg2)")

    def test_find_final_answer_not_mid_line(self):
        """FINAL mid-line (not at start) should NOT match."""

        result = find_final_answer("The result is FINAL(42)")
        assert result is None

    def test_find_final_answer_multiline_content(self):
        """FINAL with multiline content is captured."""

        text = "FINAL(This is a\nmultiline answer)"
        result = find_final_answer(text)
        assert result is not None
        assert result[0] == "final"
        assert "multiline" in result[1]

    def test_find_final_answer_bare_identifier_treated_as_var(self):
        """FINAL(python_identifier) is treated as a variable reference, not literal.

        Root cause of a real bug: when the LLM writes FINAL(final_answer)
        intending to return a variable's value, the bare-text regex parser
        cannot distinguish this from FINAL("final_answer") meaning a literal
        string. Since the sandbox is a Python REPL where FINAL(x) would
        evaluate x as a variable, bare identifiers should be treated as
        variable references (final_var), not literal strings.

        See: trace 2026-02-10T11-03-50 where the answer displayed was the
        literal string "final_answer" instead of the 38K-char report the
        LLM had stored in the `final_answer` variable.
        """

        # Single identifier — should be treated as variable reference
        result = find_final_answer("FINAL(final_answer)")
        assert result == ("final_var", "final_answer")

    def test_find_final_answer_bare_identifier_with_underscores(self):
        """FINAL(my_var_name) is treated as a variable reference."""

        result = find_final_answer("FINAL(my_report)")
        assert result == ("final_var", "my_report")

    def test_find_final_answer_bare_identifier_simple(self):
        """FINAL(result) with a simple identifier is a variable reference."""

        result = find_final_answer("FINAL(result)")
        assert result == ("final_var", "result")

    def test_find_final_answer_strips_surrounding_double_quotes(self):
        """FINAL("text") strips surrounding double quotes."""

        result = find_final_answer('FINAL("The answer is 42")')
        assert result == ("final", "The answer is 42")

    def test_find_final_answer_strips_surrounding_single_quotes(self):
        """FINAL('text') strips surrounding single quotes."""

        result = find_final_answer("FINAL('The answer is 42')")
        assert result == ("final", "The answer is 42")

    def test_find_final_answer_unescapes_newlines_in_quoted_string(self):
        r"""FINAL("line1\nline2") unescapes \n to real newlines."""

        result = find_final_answer(r'FINAL("line1\nline2")')
        assert result == ("final", "line1\nline2")

    def test_find_final_answer_number_stays_literal(self):
        """FINAL(42) with a number stays as a literal (not a valid identifier)."""

        result = find_final_answer("FINAL(42)")
        assert result == ("final", "42")

    def test_find_final_answer_expression_stays_literal(self):
        """FINAL(x + y) with operators stays as a literal."""

        result = find_final_answer("FINAL(x + y)")
        assert result == ("final", "x + y")

    def test_find_final_answer_sentence_stays_literal(self):
        """FINAL(The answer is 42) with spaces stays as a literal."""

        result = find_final_answer("FINAL(The answer is 42)")
        assert result == ("final", "The answer is 42")

    def test_find_final_answer_nested_paren_at_end_of_line_not_truncated(self):
        """FINAL(...) with nested parens at end-of-line must not truncate.

        Regression: greedy regex with re.MULTILINE matched ')' in
        '(point-by-point)' at end-of-line as the FINAL closer,
        silently dropping everything after it.  The actual bug: the
        LLM writes FINAL( with no matching close paren, and the
        content contains (nested) at end of a line, causing the regex
        to treat that ) as the FINAL closer.
        """

        # Mimics the real trace: FINAL( opens, content has (point-by-point)
        # at end of a line, then more content follows with NO closing paren
        # for FINAL.
        text = (
            "FINAL(# Analysis\n\n"
            "## Section (point-by-point)\n\n"
            "1) First item verified.\n"
            "2) Second item confirmed.\n"
        )
        result = find_final_answer(text)
        assert result is not None
        assert result[0] == "final"
        # The full content must include the numbered items AFTER (point-by-point)
        assert "Second item confirmed." in result[1]

    def test_find_final_answer_bare_final_paren_returns_none(self):
        """Bare FINAL( with no content should return None, not empty answer."""

        result = find_final_answer("FINAL(")
        assert result is None

    def test_find_final_answer_bare_final_paren_whitespace_returns_none(self):
        """FINAL( followed by only whitespace should return None."""

        result = find_final_answer("FINAL(   \n  )")
        assert result is None

    def test_find_final_answer_with_trailing_commentary(self):
        """FINAL(answer) followed by commentary on next line extracts cleanly."""

        text = "FINAL(The answer)\nSome commentary"
        result = find_final_answer(text)
        assert result is not None
        assert result[0] == "final"
        assert result[1] == "The answer"

    def test_find_final_answer_bare_partial(self):
        """Detects bare PARTIAL(text) outside code blocks."""
        result = find_final_answer("PARTIAL(Found 7 titles but no dates)")
        assert result == ("partial", "Found 7 titles but no dates")

    def test_find_final_answer_partial_strips_quotes(self):
        """PARTIAL('quoted text') strips surrounding quotes."""
        result = find_final_answer('PARTIAL("Some partial findings")')
        assert result == ("partial", "Some partial findings")

    def test_find_final_answer_partial_ignores_inside_repl_block(self):
        """Does NOT match PARTIAL inside a ```repl block (handled by executor)."""
        text = '```repl\nPARTIAL("partial findings")\n```'
        result = find_final_answer(text)
        assert result is None

    def test_find_final_answer_partial_identifier_stays_literal(self):
        """PARTIAL(findings) with a bare identifier is treated as literal text,
        NOT as a variable reference. Unlike FINAL, PARTIAL has no VAR variant."""
        result = find_final_answer("PARTIAL(findings)")
        assert result == ("partial", "findings")

    def test_find_final_answer_partial_multiline(self):
        """PARTIAL with multiline content is captured."""
        text = "PARTIAL(## Partial Findings\n\nFound some titles\n\n**Missing:** dates)"
        result = find_final_answer(text)
        assert result is not None
        assert result[0] == "partial"
        assert "Found some titles" in result[1]
        assert "Missing" in result[1]

    def test_find_final_answer_partial_with_leading_whitespace(self):
        """PARTIAL at start of line with whitespace is detected."""
        result = find_final_answer("  PARTIAL(partial text)")
        assert result == ("partial", "partial text")

    def test_find_final_answer_partial_not_mid_line(self):
        """PARTIAL mid-line (not at start) should NOT match."""
        result = find_final_answer("The result is PARTIAL(text)")
        assert result is None

    def test_find_final_answer_partial_empty_returns_none(self):
        """Bare PARTIAL( with no content should return None."""
        result = find_final_answer("PARTIAL(")
        assert result is None

    def test_find_final_answer_partial_takes_priority_over_final(self):
        """When both PARTIAL and FINAL appear, PARTIAL should match first."""
        text = "PARTIAL(partial text)\nFINAL(full answer)"
        result = find_final_answer(text)
        assert result == ("partial", "partial text")

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_resolves_bare_final_identifier_from_sandbox(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine resolves bare FINAL(var_name) by retrieving from sandbox.

        Reproduces the real bug where the LLM stored its answer in a variable
        called `final_answer` and then wrote bare text FINAL(final_answer).
        The engine should resolve this as a variable reference, not return
        the literal string "final_answer".
        """
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Iteration 0: store answer in a variable
            MagicMock(
                content='```repl\nfinal_answer = "The real detailed answer"\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Iteration 1: bare FINAL(final_answer) — intending variable ref
            MagicMock(
                content="FINAL(final_answer)",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # Iteration 0: code execution (stores variable)
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer=None,
                final_var=None,
                vars={"final_answer": "str"},
            ),
            # Iteration 1: executor retrieves variable value via print()
            MagicMock(
                status="ok",
                stdout="The real detailed answer",
                stderr="",
                error=None,
                final_answer=None,
                final_var=None,
                vars=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="What are the architectural flaws?",
        )

        # Must return the variable's VALUE, not the literal string "final_answer"
        assert result.answer == "The real detailed answer"
        assert mock_llm.complete.call_count == 2

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_retries_when_bare_final_var_lookup_fails_no_code_blocks(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine retries when bare FINAL(var) lookup fails (no code blocks).

        If the LLM writes bare FINAL(undefined_var) with no code blocks and
        the sandbox lookup fails, the engine should NOT return the variable
        name as the answer. Instead it should continue iterating with a
        helpful message so the LLM can fix its mistake.
        """
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Iteration 0: bare FINAL(undefined_var) — variable never defined
            MagicMock(
                content="FINAL(undefined_var)",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Iteration 1: LLM provides a proper literal answer
            MagicMock(
                content='FINAL("The real answer")',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # Retrieval fails — variable not defined, NameError
            MagicMock(
                status="error",
                stdout="",
                stderr="NameError: name 'undefined_var' is not defined",
                error=None,
                final_answer=None,
                final_var=None,
                vars=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="What is the answer?",
        )

        assert result.answer == "The real answer"
        assert mock_llm.complete.call_count == 2

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_retries_when_bare_final_var_lookup_fails_after_code(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine retries when bare FINAL(var) lookup fails after code execution.

        If the LLM writes a code block + bare FINAL(my_report) in the same
        response, the code block executes but doesn't define the variable
        (e.g., code bug). The sandbox lookup for my_report then fails.
        The engine should continue iterating, not return the variable name.
        """
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Iteration 0: code block + bare FINAL(my_report)
            MagicMock(
                content=(
                    "Let me analyze the document.\n\n"
                    "```repl\n"
                    'print("analyzing...")\n'
                    "```\n\n"
                    "FINAL(my_report)"
                ),
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Iteration 1: LLM provides proper answer
            MagicMock(
                content='FINAL("Actual report content")',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True

        call_count = [0]

        def execute_side_effect(code, timeout=30):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: execute the code block (doesn't define my_report)
                return MagicMock(
                    status="ok",
                    stdout="analyzing...",
                    stderr="",
                    error=None,
                    final_answer=None,
                    final_var=None,
                    vars={},
                )
            else:
                # Second call: print(my_report) — variable not defined
                return MagicMock(
                    status="error",
                    stdout="",
                    stderr="NameError: name 'my_report' is not defined",
                    error=None,
                    final_answer=None,
                    final_var=None,
                    vars=None,
                )

        mock_executor.execute.side_effect = execute_side_effect
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="What is the report?",
        )

        assert result.answer == "Actual report content"
        assert mock_llm.complete.call_count == 2

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_accepts_empty_string_from_var_resolution(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """FINAL(var) where var is "" should accept the empty string answer.

        Consistent with the `is not None` policy documented at
        _execute_code_blocks line 544-545: falsy values like FINAL(0),
        FINAL(""), FINAL(False) are valid final answers.
        """
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="FINAL(empty_var)",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            # Variable exists but print("") outputs just a newline
            status="ok",
            stdout="\n",
            stderr="",
            error=None,
            final_answer=None,
            final_var=None,
            vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="What is the answer?",
        )

        # Empty string is a valid answer (is not None policy)
        assert result.answer == ""
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_detects_bare_final_var_in_response(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine detects bare FINAL_VAR(x) and retrieves variable from sandbox."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Iteration 0: set up variable
            MagicMock(
                content='```repl\nmy_answer = "human being"\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            # Iteration 1: bare FINAL_VAR (no repl block)
            MagicMock(
                content="FINAL_VAR(my_answer)",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.side_effect = [
            # Iteration 0: code execution (no FINAL)
            MagicMock(
                status="ok",
                stdout="",
                stderr="",
                error=None,
                final_answer=None,
                final_var=None,
                vars={"my_answer": "str"},
            ),
            # Iteration 1: executor retrieves variable value
            MagicMock(
                status="ok",
                stdout="human being",
                stderr="",
                error=None,
                final_answer=None,
                final_var=None,
                vars=None,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="What is the least common label?",
        )

        assert result.answer == "human being"
        # Should only take 2 LLM calls, not burn through all 5 iterations
        assert mock_llm.complete.call_count == 2

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_detects_bare_final_in_response(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine detects bare FINAL("string") and uses it as answer."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='FINAL("the answer is 42")',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="What?",
        )

        assert result.answer == "the answer is 42"
        # Only 1 LLM call needed
        assert mock_llm.complete.call_count == 1

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_resolves_bare_final_after_code_blocks_in_same_response(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Engine executes code blocks before resolving bare FINAL(var) in same response.

        Reproduces bug where a single LLM response contains a code block
        that defines a variable AND bare FINAL(variable_name) after it.
        The code block must execute first so the variable exists in the
        sandbox when the engine tries to resolve it.

        Without the fix, the bare FINAL check fires before code execution,
        print(my_answer) raises NameError, and the fallback returns the
        literal string "my_answer" instead of the variable's value.
        """
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            # Single response: code block defining variable + bare FINAL
            MagicMock(
                content=(
                    "Here is my analysis:\n\n"
                    "```repl\n"
                    'my_answer = "The SECURITY.md is mostly accurate but..."\n'
                    "```\n\n"
                    "FINAL(my_answer)"
                ),
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True

        call_count = [0]

        def execute_side_effect(code, timeout=30):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: execute the code block (defines my_answer)
                return MagicMock(
                    status="ok",
                    stdout="",
                    stderr="",
                    error=None,
                    final_answer=None,
                    final_var=None,
                    vars={"my_answer": "str"},
                )
            else:
                # Second call: print(my_answer) — variable is now defined
                return MagicMock(
                    status="ok",
                    stdout="The SECURITY.md is mostly accurate but...",
                    stderr="",
                    error=None,
                    final_answer=None,
                    final_var=None,
                    vars=None,
                )

        mock_executor.execute.side_effect = execute_side_effect
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=5)
        result = engine.query(
            documents=["Doc content"],
            question="Is the SECURITY.md accurate?",
        )

        # Must return the variable's VALUE, not the literal "my_answer"
        assert result.answer == "The SECURITY.md is mostly accurate but..."
        assert mock_llm.complete.call_count == 1


class TestMaxIterationsFallback:
    """Tests for max-iterations LLM fallback."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_max_iterations_asks_llm_for_final_answer(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """When max iterations reached, engine asks LLM for one last answer."""
        mock_llm = MagicMock()
        responses = [
            MagicMock(
                content='```repl\nprint("exploring")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content='```repl\nprint("still exploring")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content="The answer is 42 based on my analysis.",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm.complete.side_effect = responses
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="output",
            stderr="",
            error=None,
            final_answer=None,
            final_var=None,
            vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=2)
        result = engine.query(documents=["Doc"], question="What?")

        assert result.answer == "The answer is 42 based on my analysis."
        assert mock_llm.complete.call_count == 3

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_max_iterations_fallback_uses_user_role(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ):
        """Fallback message must use 'user' role to avoid consecutive assistant msgs."""
        mock_llm = MagicMock()
        responses = [
            MagicMock(
                content='```repl\nprint("exploring")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content="The final answer.",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm.complete.side_effect = responses
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.is_alive = True
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="output",
            stderr="",
            error=None,
            final_answer=None,
            final_var=None,
            vars=None,
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model", max_iterations=1)
        engine.query(documents=["Doc"], question="What?")

        # The fallback call is the last complete() call
        fallback_call = mock_llm.complete.call_args_list[-1]
        fallback_messages = fallback_call.kwargs.get(
            "messages", fallback_call.args[0] if fallback_call.args else None
        )
        last_msg = fallback_messages[-1]
        assert last_msg["role"] == "user", (
            f"Fallback message role should be 'user', got '{last_msg['role']}'"
        )


class TestAllowBackgroundKnowledge:
    """Tests for allow_background_knowledge parameter on query()."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_passes_augmented_true_when_background_knowledge_allowed(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """query(allow_background_knowledge=True) calls render_system_prompt(augmented=True)."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        with patch.object(
            engine.prompt_loader,
            "render_system_prompt",
            wraps=engine.prompt_loader.render_system_prompt,
        ) as spy:
            engine.query(
                documents=["doc content"],
                question="What?",
                allow_background_knowledge=True,
            )
            spy.assert_called_once()
            call_kwargs = spy.call_args[1]
            assert call_kwargs.get("augmented") is True

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_query_passes_augmented_false_by_default(
        self,
        mock_llm_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """query() default calls render_system_prompt(augmented=False)."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="```repl\nFINAL('answer')\n```",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor_cls.return_value = mock_executor

        engine = RLMEngine(model="test-model")
        with patch.object(
            engine.prompt_loader,
            "render_system_prompt",
            wraps=engine.prompt_loader.render_system_prompt,
        ) as spy:
            engine.query(
                documents=["doc content"],
                question="What?",
            )
            spy.assert_called_once()
            call_kwargs = spy.call_args[1]
            assert call_kwargs.get("augmented") is False


class TestGaveUpFlag:
    """Tests for QueryResult.gave_up flag propagation."""

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_gave_up_false_for_final(
        self, mock_llm_cls: MagicMock, mock_exec_cls: MagicMock
    ):
        """QueryResult.gave_up is False when RLM returns FINAL(...)."""
        mock_llm = mock_llm_cls.return_value
        mock_llm.complete.return_value = MagicMock(
            content='FINAL(The answer is 42)',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_executor = mock_exec_cls.return_value
        mock_executor.is_alive = True
        engine = RLMEngine(model="test")
        result = engine.query(["doc content"], "question?")
        assert result.gave_up is False

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_gave_up_true_for_bare_partial(
        self, mock_llm_cls: MagicMock, mock_exec_cls: MagicMock
    ):
        """QueryResult.gave_up is True when RLM returns bare PARTIAL(...)."""
        mock_llm = mock_llm_cls.return_value
        mock_llm.complete.return_value = MagicMock(
            content='PARTIAL(Found 7 titles but no dates)',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_executor = mock_exec_cls.return_value
        mock_executor.is_alive = True
        engine = RLMEngine(model="test")
        result = engine.query(["doc content"], "question?")
        assert result.gave_up is True
        assert result.answer == "Found 7 titles but no dates"

    @patch("shesha.rlm.engine.ContainerExecutor")
    @patch("shesha.rlm.engine.LLMClient")
    def test_engine_gave_up_true_for_sandbox_partial(
        self, mock_llm_cls: MagicMock, mock_exec_cls: MagicMock
    ):
        """QueryResult.gave_up is True when sandbox returns partial_answer."""
        mock_llm = mock_llm_cls.return_value
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nPARTIAL("Found some evidence")\n```',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_executor = mock_exec_cls.return_value
        mock_executor.is_alive = True
        mock_executor.execute.return_value = ExecutionResult(
            status="ok",
            stdout="",
            stderr="",
            return_value=None,
            error=None,
            partial_answer="Found some evidence",
        )
        engine = RLMEngine(model="test")
        result = engine.query(["doc content"], "question?")
        assert result.gave_up is True
        assert result.answer == "Found some evidence"
