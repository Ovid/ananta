"""Trace writer for saving query traces to JSONL files."""

import datetime
import json
import logging
import threading
from pathlib import Path

from ananta.exceptions import TraceWriteError
from ananta.models import QueryContext
from ananta.rlm.trace import TokenUsage, TraceStep
from ananta.security.redaction import redact
from ananta.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class TraceWriter:
    """Writes query traces to JSONL files."""

    def __init__(self, storage: StorageBackend, suppress_errors: bool = False) -> None:
        """Initialize with storage backend."""
        self.storage = storage
        self.suppress_errors = suppress_errors

    def cleanup_old_traces(self, project_id: str, max_count: int = 50) -> None:
        """Remove oldest traces if count exceeds max_count.

        Args:
            project_id: The project ID
            max_count: Maximum number of traces to keep
        """
        try:
            traces = self.storage.list_traces(project_id)
            if len(traces) <= max_count:
                return

            # Sorted oldest first, delete until under limit
            to_delete = traces[: len(traces) - max_count]
            for trace_path in to_delete:
                trace_path.unlink()
        except Exception as e:
            if self.suppress_errors:
                logger.warning(f"Failed to clean up traces for project {project_id}: {e}")
                return
            raise TraceWriteError(f"Failed to clean up traces for project {project_id}: {e}") from e


class IncrementalTraceWriter:
    """Writes trace data incrementally as steps happen.

    Unlike TraceWriter which writes the entire trace at the end,
    this writer appends each step to disk as it occurs. This ensures
    partial traces are available even if the process is interrupted.
    """

    def __init__(self, storage: StorageBackend, suppress_errors: bool = False) -> None:
        """Initialize with storage backend."""
        self.storage = storage
        self.suppress_errors = suppress_errors
        self.path: Path | None = None
        self._max_iteration: int = 0
        self._finalized: bool = False
        self._lock = threading.Lock()

    @property
    def finalized(self) -> bool:
        """Whether finalize() has been called."""
        return self._finalized

    def start(self, project_id: str, context: QueryContext) -> Path | None:
        """Create trace file and write the header line.

        Args:
            project_id: The project ID.
            context: Query metadata.

        Returns:
            Path to the created file, or None if creation failed.
        """
        try:
            traces_dir = self.storage.get_traces_dir(project_id)
            now = datetime.datetime.now(datetime.UTC)
            timestamp = now.strftime("%Y-%m-%dT%H-%M-%S") + f"-{now.microsecond // 1000:03d}"
            short_id = context.trace_id[:8]
            filename = f"{timestamp}_{short_id}.jsonl"

            self.path = traces_dir / filename

            header = {
                "type": "header",
                "trace_id": context.trace_id,
                "timestamp": now.isoformat(),
                "question": context.question,
                "document_ids": context.document_ids,
                "model": context.model,
                "system_prompt": context.system_prompt,
                "subcall_prompt": context.subcall_prompt,
            }
            self.path.write_text(json.dumps(header) + "\n")
            return self.path

        except Exception as e:
            if self.suppress_errors:
                logger.warning(f"Failed to start incremental trace for project {project_id}: {e}")
                self.path = None
                return None
            raise TraceWriteError(
                f"Failed to start incremental trace for project {project_id}: {e}"
            ) from e

    def write_step(self, step: TraceStep) -> None:
        """Append a single step to the trace file.

        Args:
            step: The trace step to write.
        """
        with self._lock:
            if self.path is None or self._finalized:
                return

            try:
                self._max_iteration = max(self._max_iteration, step.iteration)
                step_data: dict[str, object] = {
                    "type": "step",
                    "step_type": step.type.value,
                    "iteration": step.iteration,
                    "timestamp": datetime.datetime.fromtimestamp(
                        step.timestamp, tz=datetime.UTC
                    ).isoformat(),
                    "content": redact(step.content),
                    "tokens_used": step.tokens_used,
                    "duration_ms": step.duration_ms,
                }
                if step.metadata:
                    step_data["metadata"] = step.metadata
                with self.path.open("a") as f:
                    f.write(json.dumps(step_data) + "\n")
            except Exception as e:
                if self.suppress_errors:
                    logger.warning(f"Failed to write incremental trace step: {e}")
                    return
                raise TraceWriteError(f"Failed to write incremental trace step: {e}") from e

    def finalize(
        self,
        answer: str,
        token_usage: TokenUsage,
        execution_time: float,
        status: str,
    ) -> None:
        """Append summary line to the trace file.

        Args:
            answer: The final answer (or partial state).
            token_usage: Token usage statistics.
            execution_time: Total execution time in seconds.
            status: Query status (success, max_iterations, interrupted).
        """
        with self._lock:
            if self.path is None or self._finalized:
                return

            try:
                summary = {
                    "type": "summary",
                    "answer": answer,
                    "total_iterations": self._max_iteration + 1,
                    "total_tokens": {
                        "prompt": token_usage.prompt_tokens,
                        "completion": token_usage.completion_tokens,
                    },
                    "total_duration_ms": int(execution_time * 1000),
                    "status": status,
                }
                with self.path.open("a") as f:
                    f.write(json.dumps(summary) + "\n")
                self._finalized = True
            except Exception as e:
                if self.suppress_errors:
                    # Mark as finalized even on failure to prevent a later
                    # safety-net call from overwriting with "[interrupted]".
                    self._finalized = True
                    logger.warning(f"Failed to finalize incremental trace: {e}")
                    return
                raise TraceWriteError(f"Failed to finalize incremental trace: {e}") from e
