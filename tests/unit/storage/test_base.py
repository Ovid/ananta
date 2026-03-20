"""Tests for storage base classes."""

from ananta.storage.base import ParsedDocument, StorageBackend


def test_parsed_document_creation():
    """ParsedDocument stores document metadata and content."""
    doc = ParsedDocument(
        name="test.txt",
        content="Hello world",
        format="txt",
        metadata={"encoding": "utf-8"},
        char_count=11,
        parse_warnings=[],
    )
    assert doc.name == "test.txt"
    assert doc.content == "Hello world"
    assert doc.char_count == 11


class TestStorageBackendProtocol:
    """Tests for StorageBackend protocol definition."""

    def test_protocol_has_store_analysis_method(self):
        """StorageBackend protocol includes store_analysis method."""
        assert hasattr(StorageBackend, "store_analysis")

    def test_protocol_has_load_analysis_method(self):
        """StorageBackend protocol includes load_analysis method."""
        assert hasattr(StorageBackend, "load_analysis")

    def test_protocol_has_delete_analysis_method(self):
        """StorageBackend protocol includes delete_analysis method."""
        assert hasattr(StorageBackend, "delete_analysis")

    def test_protocol_has_get_traces_dir_method(self):
        """StorageBackend protocol includes get_traces_dir method."""
        assert hasattr(StorageBackend, "get_traces_dir")

    def test_protocol_has_list_traces_method(self):
        """StorageBackend protocol includes list_traces method."""
        assert hasattr(StorageBackend, "list_traces")
