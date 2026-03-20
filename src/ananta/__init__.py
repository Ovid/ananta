"""Ananta: Recursive Language Models for document querying."""

from ananta.ananta import Ananta
from ananta.config import AnantaConfig
from ananta.exceptions import (
    AnantaError,
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
    TraceWriteError,
)
from ananta.models import ParsedDocument, ProjectInfo, QueryContext, RepoProjectResult
from ananta.project import Project
from ananta.rlm import ProgressCallback, QueryResult, StepType, TokenUsage, Trace, TraceStep
from ananta.storage import FilesystemStorage

try:
    from ananta._version import __version__
except ImportError:
    __version__ = "0.0.0.dev0"  # Fallback before package is built

__all__ = [
    "__version__",
    # Main API
    "Ananta",
    "Project",
    "AnantaConfig",
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
    "AnantaError",
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
