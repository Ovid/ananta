"""Shesha: Recursive Language Models for document querying."""

from shesha.config import SheshaConfig
from shesha.exceptions import (
    AuthenticationError,
    DocumentError,
    DocumentNotFoundError,
    EngineNotConfiguredError,
    NoParserError,
    ParseError,
    ProjectError,
    ProjectExistsError,
    ProjectNotFoundError,
    RepoError,
    RepoIngestError,
    SheshaError,
    TraceWriteError,
)
from shesha.models import ParsedDocument, ProjectInfo, QueryContext, RepoProjectResult
from shesha.project import Project
from shesha.rlm import ProgressCallback, QueryResult, StepType, TokenUsage, Trace, TraceStep
from shesha.shesha import Shesha
from shesha.storage import FilesystemStorage

try:
    from shesha._version import __version__
except ImportError:
    __version__ = "0.0.0.dev0"  # Fallback before package is built

__all__ = [
    "__version__",
    # Main API
    "Shesha",
    "Project",
    "SheshaConfig",
    # Query results
    "ProgressCallback",
    "QueryContext",
    "QueryResult",
    "RepoProjectResult",
    "Trace",
    "TraceStep",
    "StepType",
    "TokenUsage",
    # Storage
    "FilesystemStorage",
    "ParsedDocument",
    "ProjectInfo",
    # Exceptions
    "SheshaError",
    "ProjectError",
    "ProjectNotFoundError",
    "ProjectExistsError",
    "DocumentError",
    "DocumentNotFoundError",
    "ParseError",
    "NoParserError",
    "RepoError",
    "AuthenticationError",
    "RepoIngestError",
    "TraceWriteError",
    "EngineNotConfiguredError",
]
