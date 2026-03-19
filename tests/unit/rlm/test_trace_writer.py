"""Tests for trace writer."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shesha.exceptions import TraceWriteError
from shesha.models import QueryContext
from shesha.rlm.trace import StepType, TokenUsage, Trace
from shesha.storage.filesystem import FilesystemStorage


class TestTraceWriterCleanup:
    """Tests for trace cleanup."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> FilesystemStorage:
        """Create a temporary storage backend."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")
        return storage

    def test_cleanup_removes_oldest_traces(self, storage: FilesystemStorage) -> None:
        """cleanup_old_traces removes oldest when over limit."""
        from shesha.rlm.trace_writer import TraceWriter

        traces_dir = storage.get_traces_dir("test-project")
        # Create 5 trace files
        for i in range(5):
            (traces_dir / f"2026-02-03T10-00-0{i}-000_aaaa{i}111.jsonl").write_text("{}")

        writer = TraceWriter(storage)
        writer.cleanup_old_traces("test-project", max_count=3)

        remaining = storage.list_traces("test-project")
        assert len(remaining) == 3
        # Oldest 2 should be deleted, newest 3 remain
        names = [p.name for p in remaining]
        assert "2026-02-03T10-00-02-000_aaaa2111.jsonl" in names
        assert "2026-02-03T10-00-03-000_aaaa3111.jsonl" in names
        assert "2026-02-03T10-00-04-000_aaaa4111.jsonl" in names

    def test_cleanup_does_nothing_under_limit(self, storage: FilesystemStorage) -> None:
        """cleanup_old_traces does nothing when under limit."""
        from shesha.rlm.trace_writer import TraceWriter

        traces_dir = storage.get_traces_dir("test-project")
        # Create 2 trace files
        (traces_dir / "2026-02-03T10-00-00-000_aaaa1111.jsonl").write_text("{}")
        (traces_dir / "2026-02-03T10-00-01-000_bbbb2222.jsonl").write_text("{}")

        writer = TraceWriter(storage)
        writer.cleanup_old_traces("test-project", max_count=5)

        remaining = storage.list_traces("test-project")
        assert len(remaining) == 2


class TestCleanupOldTracesErrorHandling:
    """Tests for cleanup_old_traces error handling."""

    def test_cleanup_raises_by_default_on_error(self, tmp_path: Path) -> None:
        """cleanup_old_traces raises TraceWriteError when suppress_errors is False."""
        from shesha.exceptions import TraceWriteError
        from shesha.rlm.trace_writer import TraceWriter

        storage = MagicMock()
        storage.list_traces.side_effect = OSError("disk error")

        writer = TraceWriter(storage, suppress_errors=False)
        with pytest.raises(TraceWriteError):
            writer.cleanup_old_traces("test-project", max_count=3)

    def test_cleanup_suppresses_errors_when_configured(self, tmp_path: Path) -> None:
        """cleanup_old_traces swallows errors when suppress_errors is True."""
        from shesha.rlm.trace_writer import TraceWriter

        storage = MagicMock()
        storage.list_traces.side_effect = OSError("disk error")

        writer = TraceWriter(storage, suppress_errors=True)
        # Should not raise
        writer.cleanup_old_traces("test-project", max_count=3)


class TestIncrementalTraceWriter:
    """Tests for IncrementalTraceWriter."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> FilesystemStorage:
        """Create a temporary storage backend."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("test-project")
        return storage

    @pytest.fixture
    def context(self) -> QueryContext:
        """Create a sample query context."""
        return QueryContext(
            trace_id="abcd1234-5678-90ab-cdef-1234567890ab",
            question="What is the answer?",
            document_ids=["doc1", "doc2"],
            model="claude-sonnet-4-20250514",
            system_prompt="You are an assistant...",
            subcall_prompt="Analyze this...",
        )

    def test_start_creates_file_with_header(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """start() creates a JSONL file with header as first line."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        path = writer.start("test-project", context)

        assert path is not None
        assert path.exists()
        assert path.suffix == ".jsonl"

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        header = json.loads(lines[0])
        assert header["type"] == "header"
        assert header["question"] == "What is the answer?"
        assert header["trace_id"] == "abcd1234-5678-90ab-cdef-1234567890ab"

    def test_write_step_appends_to_file(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """write_step() appends a step line after the header."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        step = Trace().add_step(StepType.CODE_GENERATED, "print('hi')", iteration=0, tokens_used=50)
        writer.write_step(step)

        lines = writer.path.read_text().strip().split("\n")
        assert len(lines) == 2  # header + 1 step

        step_data = json.loads(lines[1])
        assert step_data["type"] == "step"
        assert step_data["step_type"] == "code_generated"
        assert step_data["content"] == "print('hi')"
        assert step_data["tokens_used"] == 50

    def test_multiple_steps_appended_in_order(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """Multiple write_step() calls append in order."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        trace = Trace()
        step1 = trace.add_step(StepType.CODE_GENERATED, "code1", iteration=0)
        writer.write_step(step1)
        step2 = trace.add_step(StepType.CODE_OUTPUT, "output1", iteration=0)
        writer.write_step(step2)
        step3 = trace.add_step(StepType.SUBCALL_REQUEST, "request", iteration=0)
        writer.write_step(step3)

        lines = writer.path.read_text().strip().split("\n")
        assert len(lines) == 4  # header + 3 steps

        assert json.loads(lines[1])["step_type"] == "code_generated"
        assert json.loads(lines[2])["step_type"] == "code_output"
        assert json.loads(lines[3])["step_type"] == "subcall_request"

    def test_finalize_appends_summary(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """finalize() appends summary as last line."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        step = Trace().add_step(StepType.CODE_GENERATED, "code", iteration=0)
        writer.write_step(step)

        writer.finalize(
            answer="42",
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            execution_time=1.5,
            status="success",
        )

        lines = writer.path.read_text().strip().split("\n")
        summary = json.loads(lines[-1])
        assert summary["type"] == "summary"
        assert summary["answer"] == "42"
        assert summary["status"] == "success"
        assert summary["total_tokens"] == {"prompt": 100, "completion": 50}
        assert summary["total_duration_ms"] == 1500

    def test_finalize_without_steps_writes_interrupted_summary(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """finalize() works even with no steps (e.g., early interruption)."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        writer.finalize(
            answer="[interrupted]",
            token_usage=TokenUsage(),
            execution_time=0.5,
            status="interrupted",
        )

        lines = writer.path.read_text().strip().split("\n")
        assert len(lines) == 2  # header + summary
        summary = json.loads(lines[-1])
        assert summary["status"] == "interrupted"

    def test_steps_are_redacted(self, storage: FilesystemStorage, context: QueryContext) -> None:
        """Secrets in step content are redacted before writing."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        step = Trace().add_step(
            StepType.CODE_OUTPUT,
            "API key: sk-abc123def456ghi789jkl012mno345pqr678",
            iteration=0,
        )
        writer.write_step(step)

        content = writer.path.read_text()
        assert "sk-abc123" not in content
        assert "[REDACTED]" in content

    def test_write_step_noop_when_not_started(self) -> None:
        """write_step() is a no-op if start() was never called."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(MagicMock())
        step = Trace().add_step(StepType.CODE_GENERATED, "code", iteration=0)
        # Should not raise
        writer.write_step(step)

    def test_finalize_noop_when_not_started(self) -> None:
        """finalize() is a no-op if start() was never called."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(MagicMock())
        # Should not raise
        writer.finalize(
            answer="x",
            token_usage=TokenUsage(),
            execution_time=0.0,
            status="error",
        )

    def test_start_raises_by_default_on_failure(self, context: QueryContext) -> None:
        """start() raises TraceWriteError by default on failure."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        mock_storage = MagicMock()
        mock_storage.get_traces_dir.side_effect = OSError("no traces dir")

        writer = IncrementalTraceWriter(mock_storage)
        with pytest.raises(TraceWriteError):
            writer.start("test-project", context)

    def test_start_returns_none_when_suppressed(self, context: QueryContext) -> None:
        """start() returns None when suppress_errors=True on failure."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        mock_storage = MagicMock()
        mock_storage.get_traces_dir.side_effect = OSError("no traces dir")

        writer = IncrementalTraceWriter(mock_storage, suppress_errors=True)
        result = writer.start("test-project", context)
        assert result is None

    def test_write_step_raises_by_default_on_failure(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """write_step() raises TraceWriteError by default on failure."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        # Make file read-only to force write failure
        writer.path.chmod(0o444)

        step = Trace().add_step(StepType.CODE_GENERATED, "code", iteration=0)
        try:
            with pytest.raises(TraceWriteError):
                writer.write_step(step)
        finally:
            writer.path.chmod(0o644)

    def test_write_step_suppresses_when_configured(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """write_step() logs warning when suppress_errors=True on failure."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage, suppress_errors=True)
        writer.start("test-project", context)

        # Make file read-only to force write failure
        writer.path.chmod(0o444)

        step = Trace().add_step(StepType.CODE_GENERATED, "code", iteration=0)
        try:
            # Should not raise
            writer.write_step(step)
        finally:
            writer.path.chmod(0o644)

    def test_finalize_raises_by_default_on_failure(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """finalize() raises TraceWriteError by default on failure."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        # Make file read-only to force write failure
        writer.path.chmod(0o444)

        try:
            with pytest.raises(TraceWriteError):
                writer.finalize(
                    answer="x",
                    token_usage=TokenUsage(),
                    execution_time=0.0,
                    status="error",
                )
        finally:
            writer.path.chmod(0o644)

    def test_finalize_suppresses_when_configured(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """finalize() logs warning when suppress_errors=True on failure."""
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage, suppress_errors=True)
        writer.start("test-project", context)

        # Make file read-only to force write failure
        writer.path.chmod(0o444)

        try:
            # Should not raise
            writer.finalize(
                answer="x",
                token_usage=TokenUsage(),
                execution_time=0.0,
                status="error",
            )
        finally:
            writer.path.chmod(0o644)

    def test_write_step_after_finalize_is_noop(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """write_step() after finalize() should not append to the trace file.

        Safety-net test for F-15: verifies temporal coupling behavior so that
        adding state enforcement doesn't silently change semantics.
        """
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        step = Trace().add_step(StepType.CODE_GENERATED, "code", iteration=0)
        writer.write_step(step)

        writer.finalize(
            answer="42",
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            execution_time=1.5,
            status="success",
        )

        lines_after_finalize = writer.path.read_text().strip().split("\n")
        assert len(lines_after_finalize) == 3  # header + step + summary

        # Currently write_step after finalize still appends (no enforcement).
        # This test documents that behavior so the fix can change it safely.
        late_step = Trace().add_step(StepType.CODE_OUTPUT, "late", iteration=1)
        writer.write_step(late_step)

        lines_after_late = writer.path.read_text().strip().split("\n")
        # Currently 4 lines (no enforcement), fix should make this stay at 3
        assert len(lines_after_late) == 4

    def test_finalize_after_finalize_appends_duplicate(
        self, storage: FilesystemStorage, context: QueryContext
    ) -> None:
        """Calling finalize() twice currently appends a duplicate summary.

        Safety-net test for F-15: documents current behavior.
        """
        from shesha.rlm.trace_writer import IncrementalTraceWriter

        writer = IncrementalTraceWriter(storage)
        writer.start("test-project", context)

        writer.finalize(
            answer="first",
            token_usage=TokenUsage(),
            execution_time=1.0,
            status="success",
        )
        writer.finalize(
            answer="second",
            token_usage=TokenUsage(),
            execution_time=2.0,
            status="success",
        )

        lines = writer.path.read_text().strip().split("\n")
        # Currently 3 lines: header + 2 summaries (no enforcement)
        assert len(lines) == 3
        summaries = [json.loads(l) for l in lines if json.loads(l)["type"] == "summary"]
        assert len(summaries) == 2
