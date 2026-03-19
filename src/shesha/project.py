"""Project class for managing document collections."""

import logging
import threading
from pathlib import Path

from shesha.exceptions import EngineNotConfiguredError
from shesha.models import ParsedDocument
from shesha.parser.registry import ParserRegistry
from shesha.rlm.engine import ProgressCallback, QueryResult, RLMEngine
from shesha.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class Project:
    """A project containing documents for querying."""

    def __init__(
        self,
        project_id: str,
        storage: StorageBackend,
        parser_registry: ParserRegistry,
        rlm_engine: RLMEngine | None = None,
    ) -> None:
        """Initialize a project."""
        self.project_id = project_id
        self._storage = storage
        self._parser_registry = parser_registry
        self._rlm_engine = rlm_engine

    @property
    def rlm_engine(self) -> RLMEngine | None:
        """The RLM engine for this project, or None if not configured."""
        return self._rlm_engine

    @property
    def parser_registry(self) -> ParserRegistry:
        """The parser registry for this project."""
        return self._parser_registry

    def upload(self, path: Path | str, recursive: bool = False) -> list[str]:
        """Upload a file or directory to the project."""
        path = Path(path)
        uploaded: list[str] = []

        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            files = [f for f in path.glob(pattern) if f.is_file()]
        else:
            files = [path]

        for file_path in files:
            parser = self._parser_registry.find_parser(file_path)
            if parser is None:
                continue  # Skip unsupported files

            doc = parser.parse(file_path)
            if path.is_dir():
                relative_name = file_path.relative_to(path).as_posix()
                doc = ParsedDocument(
                    name=relative_name,
                    content=doc.content,
                    format=doc.format,
                    metadata=doc.metadata,
                    char_count=doc.char_count,
                    parse_warnings=doc.parse_warnings,
                )
            self._storage.store_document(self.project_id, doc, raw_path=file_path)
            uploaded.append(doc.name)

        return uploaded

    def list_documents(self) -> list[str]:
        """List all documents in the project."""
        return self._storage.list_documents(self.project_id)

    def delete_document(self, doc_name: str) -> None:
        """Delete a document from the project."""
        self._storage.delete_document(self.project_id, doc_name)

    def query(
        self,
        question: str,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> QueryResult:
        """Query the documents with a question."""
        if self._rlm_engine is None:
            raise EngineNotConfiguredError()

        docs = self._storage.load_all_documents(self.project_id)
        logger.info("Querying project %s (%d docs)", self.project_id, len(docs))
        return self._rlm_engine.query(
            documents=[d.content for d in docs],
            question=question,
            doc_names=[d.name for d in docs],
            on_progress=on_progress,
            storage=self._storage,
            project_id=self.project_id,
            cancel_event=cancel_event,
        )
