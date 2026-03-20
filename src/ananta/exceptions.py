"""Shesha domain exceptions."""


class SheshaError(Exception):
    """Base exception for all Shesha errors."""


class ProjectError(SheshaError):
    """Base exception for project-related errors."""


class ProjectNotFoundError(ProjectError):
    """Raised when a project does not exist."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"Project '{project_id}' does not exist")


class ProjectExistsError(ProjectError):
    """Raised when trying to create a project that already exists."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"Project '{project_id}' already exists")


class DocumentError(SheshaError):
    """Base exception for document-related errors."""


class DocumentNotFoundError(DocumentError):
    """Raised when a document does not exist."""

    def __init__(self, project_id: str, doc_name: str) -> None:
        self.project_id = project_id
        self.doc_name = doc_name
        super().__init__(f"Document '{doc_name}' not found in project '{project_id}'")


class ParseError(SheshaError):
    """Raised when document parsing fails."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to parse '{path}': {reason}")


class NoParserError(SheshaError):
    """Raised when no parser can handle a file."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"No parser available for '{path}'")


class RepoError(SheshaError):
    """Base exception for repository-related errors."""


class AuthenticationError(RepoError):
    """Raised when repository authentication fails."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(
            f"Authentication failed for '{url}'. "
            "Pass `token=` parameter or set GITHUB_TOKEN/GITLAB_TOKEN/BITBUCKET_TOKEN "
            "environment variable."
        )


class RepoIngestError(RepoError):
    """Raised when repository ingestion fails."""

    def __init__(self, url: str, cause: Exception | None = None) -> None:
        self.url = url
        msg = f"Failed to ingest repository '{url}'"
        if cause:
            msg += f": {cause}"
        super().__init__(msg)
        if cause:
            self.__cause__ = cause


class TraceWriteError(SheshaError):
    """Raised when writing a trace fails."""


class EngineNotConfiguredError(SheshaError):
    """Raised when a query is attempted without an RLM engine."""

    def __init__(self) -> None:
        super().__init__("No RLM engine configured for queries")
