"""Storage backend for Ananta."""

from ananta.models import ParsedDocument
from ananta.storage.base import StorageBackend
from ananta.storage.filesystem import FilesystemStorage

__all__ = ["FilesystemStorage", "ParsedDocument", "StorageBackend"]
