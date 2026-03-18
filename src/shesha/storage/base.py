"""Storage backend protocol and data classes."""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from shesha.models import ParsedDocument

if TYPE_CHECKING:
    from shesha.models import RepoAnalysis


class StorageBackend(Protocol):
    """Protocol for pluggable storage backends."""

    def create_project(self, project_id: str) -> None:
        """Create a new project."""
        ...

    def delete_project(self, project_id: str) -> None:
        """Delete a project and all its documents."""
        ...

    def list_projects(self) -> list[str]:
        """List all project IDs."""
        ...

    def project_exists(self, project_id: str) -> bool:
        """Check if a project exists."""
        ...

    def store_document(
        self, project_id: str, doc: ParsedDocument, raw_path: Path | None = None
    ) -> None:
        """Store a parsed document in a project.

        Args:
            project_id: The project to store the document in.
            doc: The parsed document to store.
            raw_path: Optional path to the original file for raw storage.
        """
        ...

    def get_document(self, project_id: str, doc_name: str) -> ParsedDocument:
        """Retrieve a document by name."""
        ...

    def list_documents(self, project_id: str) -> list[str]:
        """List all document names in a project."""
        ...

    def delete_document(self, project_id: str, doc_name: str) -> None:
        """Delete a document from a project."""
        ...

    def load_all_documents(self, project_id: str) -> list[ParsedDocument]:
        """Load all documents in a project for querying."""
        ...

    def get_project_dir(self, project_id: str) -> Path:
        """Get the root directory for a project."""
        ...

    def get_traces_dir(self, project_id: str) -> Path:
        """Get the traces directory for a project, creating it if needed."""
        ...

    def list_traces(self, project_id: str) -> list[Path]:
        """List all trace files in a project, sorted by name (oldest first)."""
        ...

    def store_analysis(self, project_id: str, analysis: "RepoAnalysis") -> None:
        """Store a codebase analysis for a project."""
        ...

    def load_analysis(self, project_id: str) -> "RepoAnalysis | None":
        """Load the codebase analysis for a project."""
        ...

    def delete_analysis(self, project_id: str) -> None:
        """Delete the codebase analysis for a project."""
        ...


# Re-export ParsedDocument for backwards compatibility
__all__ = ["ParsedDocument", "StorageBackend"]
