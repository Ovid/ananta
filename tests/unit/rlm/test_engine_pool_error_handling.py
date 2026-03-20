"""Tests for engine pool error handling when reset_namespace fails."""

from unittest.mock import MagicMock, patch

from ananta.rlm.engine import RLMEngine
from ananta.sandbox.pool import ContainerPool


class TestPoolExecutorErrorHandling:
    """Tests for handling broken executors in pool-backed queries."""

    def _make_engine_with_pool(
        self,
        mock_llm_cls: MagicMock,
        mock_executor: MagicMock,
    ) -> tuple[RLMEngine, MagicMock]:
        """Create engine with mock pool and executor."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content='```repl\nFINAL("answer")\n```',
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_llm_cls.return_value = mock_llm

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.acquire.return_value = mock_executor

        engine = RLMEngine(model="test-model", pool=mock_pool)
        return engine, mock_pool

    @patch("ananta.rlm.engine.LLMClient")
    def test_broken_executor_not_released_to_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When reset_namespace raises, executor is discarded, not released."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor.reset_namespace.side_effect = RuntimeError("No socket connection")

        engine, mock_pool = self._make_engine_with_pool(mock_llm_cls, mock_executor)
        engine.query(documents=["doc"], question="Q?")

        # Broken executor should be stopped, not released
        mock_executor.stop.assert_called_once()
        mock_pool.release.assert_not_called()
        mock_pool.discard.assert_called_once_with(mock_executor)

    @patch("ananta.rlm.engine.LLMClient")
    def test_healthy_executor_released_to_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """When reset_namespace succeeds, executor is released normally."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )

        engine, mock_pool = self._make_engine_with_pool(mock_llm_cls, mock_executor)
        engine.query(documents=["doc"], question="Q?")

        # Healthy executor should be released, not stopped
        mock_pool.release.assert_called_once_with(mock_executor)
        mock_executor.stop.assert_not_called()

    @patch("ananta.rlm.engine.LLMClient")
    def test_query_result_not_masked_by_reset_failure(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Query result is returned even when reset_namespace fails."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            status="ok",
            stdout="",
            stderr="",
            error=None,
            final_answer="answer",
        )
        mock_executor.reset_namespace.side_effect = RuntimeError("No socket connection")

        engine, mock_pool = self._make_engine_with_pool(mock_llm_cls, mock_executor)
        result = engine.query(documents=["doc"], question="Q?")

        # Should still get the answer
        assert result.answer == "answer"


class TestDeadExecutorRecovery:
    """Tests for mid-loop dead executor recovery with pool."""

    @patch("ananta.rlm.engine.LLMClient")
    def test_dead_executor_replaced_from_pool(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Dead executor is replaced from pool and query succeeds on next iteration."""
        from ananta.sandbox.executor import ExecutionResult

        mock_pool = MagicMock(spec=ContainerPool)

        # First executor: dies after protocol error (is_alive=False)
        dead_executor = MagicMock()
        dead_executor.is_alive = True  # starts alive
        dead_executor.execute.return_value = ExecutionResult(
            status="error",
            stdout="",
            stderr="",
            return_value=None,
            error="Protocol error: line too long",
        )

        # After execute, mark as dead (simulating stop() called by execute)
        def kill_on_execute(code, timeout=30):
            dead_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error: line too long",
            )

        dead_executor.execute.side_effect = kill_on_execute

        # Fresh executor: works fine
        fresh_executor = MagicMock()
        fresh_executor.is_alive = True
        fresh_executor.execute.return_value = ExecutionResult(
            status="ok",
            stdout="",
            stderr="",
            return_value=None,
            error=None,
            final_answer="recovered answer",
        )

        mock_pool.acquire.side_effect = [dead_executor, fresh_executor]

        # LLM: first call produces code that triggers error, second call produces FINAL
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content='```repl\nprint("big output")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content='```repl\nFINAL("recovered answer")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        engine = RLMEngine(model="test-model", pool=mock_pool)
        result = engine.query(documents=["doc"], question="Q?")

        assert result.answer == "recovered answer"
        # Pool should have been asked for a second executor
        assert mock_pool.acquire.call_count == 2
        mock_pool.discard.assert_called_once_with(dead_executor)

    @patch("ananta.rlm.engine.LLMClient")
    def test_fresh_executor_gets_llm_query_handler(
        self,
        mock_llm_cls: MagicMock,
    ):
        """Fresh replacement executor gets llm_query_handler set."""
        from ananta.sandbox.executor import ExecutionResult

        mock_pool = MagicMock(spec=ContainerPool)

        # Dead executor
        dead_executor = MagicMock()
        dead_executor.is_alive = True

        def kill_on_execute(code, timeout=30):
            dead_executor.is_alive = False
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Protocol error: overflow",
            )

        dead_executor.execute.side_effect = kill_on_execute

        # Fresh executor
        fresh_executor = MagicMock()
        fresh_executor.is_alive = True
        fresh_executor.execute.return_value = ExecutionResult(
            status="ok",
            stdout="",
            stderr="",
            return_value=None,
            error=None,
            final_answer="answer",
        )

        mock_pool.acquire.side_effect = [dead_executor, fresh_executor]

        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            MagicMock(
                content='```repl\nprint("boom")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            MagicMock(
                content='```repl\nFINAL("answer")\n```',
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        ]
        mock_llm_cls.return_value = mock_llm

        engine = RLMEngine(model="test-model", pool=mock_pool)

        # Track llm_query_handler assignments on fresh_executor
        handler_values: list[object] = []
        original_setattr = type(fresh_executor).__setattr__

        def track_handler(self, name, value):
            if name == "llm_query_handler":
                handler_values.append(value)
            original_setattr(self, name, value)

        with patch.object(type(fresh_executor), "__setattr__", track_handler):
            engine.query(documents=["doc"], question="Q?")

        # Handler should have been set (first set is callable, last is None from cleanup)
        assert len(handler_values) >= 1
        assert callable(handler_values[0])
        # Fresh executor should have had setup_context called with wrapped documents
        fresh_executor.setup_context.assert_called_once()
        call_args = fresh_executor.setup_context.call_args[0][0]
        assert len(call_args) == 1
        assert "doc" in call_args[0]
        assert "_BEGIN" in call_args[0]
        assert "_END" in call_args[0]


class TestPoolDiscard:
    """Tests for ContainerPool.discard method."""

    def test_discard_removes_from_in_use(self):
        """discard() removes executor from _in_use without adding to _available."""
        pool = ContainerPool.__new__(ContainerPool)
        pool._lock = __import__("threading").Lock()
        pool._available = __import__("collections").deque()
        pool._in_use = set()

        mock_executor = MagicMock()
        pool._in_use.add(mock_executor)

        pool.discard(mock_executor)

        assert mock_executor not in pool._in_use
        assert mock_executor not in pool._available

    def test_discard_unknown_executor_is_safe(self):
        """discard() does not raise for unknown executors."""
        pool = ContainerPool.__new__(ContainerPool)
        pool._lock = __import__("threading").Lock()
        pool._available = __import__("collections").deque()
        pool._in_use = set()

        mock_executor = MagicMock()
        # Should not raise
        pool.discard(mock_executor)
