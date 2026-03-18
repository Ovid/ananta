"""Persistent conversation session for the web interface."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERSATION_FILE = "conversation.json"


class WebConversationSession:
    """Manages conversation history with JSON file persistence."""

    def __init__(self, project_dir: Path, conversation_file: str = CONVERSATION_FILE) -> None:
        self._file = project_dir / conversation_file
        self._exchanges: list[dict[str, object]] = []
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._exchanges = data.get("exchanges", [])
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt conversation file %s; starting empty", self._file)
                self._exchanges = []

    def _save(self) -> None:
        data = json.dumps({"exchanges": self._exchanges}, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._file.parent, prefix=self._file.name + ".")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.replace(tmp, self._file)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def add_exchange(
        self,
        *,
        question: str,
        answer: str,
        trace_id: str | None,
        tokens: dict[str, int],
        execution_time: float,
        model: str,
        document_ids: list[str] | None = None,
        allow_background_knowledge: bool = False,
    ) -> dict[str, object]:
        exchange: dict[str, object] = {
            "exchange_id": str(uuid.uuid4()),
            "question": question,
            "answer": answer,
            "trace_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "tokens": tokens,
            "execution_time": execution_time,
            "model": model,
            "document_ids": document_ids,
            "allow_background_knowledge": allow_background_knowledge,
        }
        self._exchanges.append(exchange)
        self._save()
        return exchange

    def list_exchanges(self) -> list[dict[str, object]]:
        return list(self._exchanges)

    def clear(self) -> None:
        self._exchanges = []
        self._save()

    def format_history_prefix(self) -> str:
        if not self._exchanges:
            return ""
        lines = ["Previous conversation:"]
        for i, ex in enumerate(self._exchanges, 1):
            lines.append(f"Q{i}: {ex['question']}")
            lines.append(f"A{i}: {ex['answer']}")
            lines.append("")
        lines.append("Current question:\n")
        return "\n".join(lines)

    def format_transcript(self) -> str:
        lines = ["# Conversation Transcript\n"]
        lines.append(f"Exported: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n")
        for ex in self._exchanges:
            lines.append(f"**Q:** {ex['question']}\n")
            lines.append(f"**A:** {ex['answer']}\n")
            if ex.get("tokens"):
                t = ex["tokens"]
                assert isinstance(t, dict)
                lines.append(
                    f"*Tokens: {t.get('total', 0)} "
                    f"(prompt: {t.get('prompt', 0)}, "
                    f"completion: {t.get('completion', 0)}) | "
                    f"Time: {ex.get('execution_time', 0):.1f}s*\n"
                )
            lines.append("---\n")
        return "\n".join(lines)

    def context_chars(self) -> int:
        total = 0
        for ex in self._exchanges:
            total += len(str(ex.get("question", "")))
            total += len(str(ex.get("answer", "")))
        return total
