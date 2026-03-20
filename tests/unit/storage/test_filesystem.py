"""Tests for filesystem storage backend."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from ananta.exceptions import (
    DocumentNotFoundError,
    ProjectExistsError,
    ProjectNotFoundError,
)
from ananta.models import (
    AnalysisComponent,
    AnalysisExternalDep,
    ParsedDocument,
    RepoAnalysis,
)
from ananta.security.paths import PathTraversalError
from ananta.storage.filesystem import FilesystemStorage


@pytest.fixture
def storage(tmp_path: Path) -> FilesystemStorage:
    """Create a temporary storage backend."""
    return FilesystemStorage(root_path=tmp_path)


class TestProjectOperations:
    """Tests for project CRUD operations."""

    def test_create_project(self, storage: FilesystemStorage):
        """Creating a project creates the directory structure."""
        storage.create_project("test-project")
        assert storage.project_exists("test-project")

    def test_list_projects_empty(self, storage: FilesystemStorage):
        """List projects returns empty list when none exist."""
        assert storage.list_projects() == []

    def test_list_projects(self, storage: FilesystemStorage):
        """List projects returns all project IDs."""
        storage.create_project("project-a")
        storage.create_project("project-b")
        projects = storage.list_projects()
        assert sorted(projects) == ["project-a", "project-b"]

    def test_delete_project(self, storage: FilesystemStorage):
        """Deleting a project removes it completely."""
        storage.create_project("to-delete")
        storage.delete_project("to-delete")
        assert not storage.project_exists("to-delete")

    def test_create_duplicate_project_raises(self, storage: FilesystemStorage):
        """Creating a project that exists raises an error."""
        storage.create_project("existing")
        with pytest.raises(ProjectExistsError):
            storage.create_project("existing")


class TestDocumentOperations:
    """Tests for document CRUD operations."""

    def test_store_and_retrieve_document(self, storage: FilesystemStorage):
        """Storing a document allows retrieval."""
        storage.create_project("docs-project")
        doc = ParsedDocument(
            name="test.txt",
            content="Hello world",
            format="txt",
            metadata={"encoding": "utf-8"},
            char_count=11,
            parse_warnings=[],
        )
        storage.store_document("docs-project", doc)
        retrieved = storage.get_document("docs-project", "test.txt")
        assert retrieved.name == doc.name
        assert retrieved.content == doc.content

    def test_list_documents(self, storage: FilesystemStorage):
        """List documents returns all document names."""
        storage.create_project("list-project")
        for name in ["a.txt", "b.txt", "c.txt"]:
            doc = ParsedDocument(
                name=name,
                content=f"Content of {name}",
                format="txt",
                metadata={},
                char_count=len(f"Content of {name}"),
                parse_warnings=[],
            )
            storage.store_document("list-project", doc)
        docs = storage.list_documents("list-project")
        assert sorted(docs) == ["a.txt", "b.txt", "c.txt"]

    def test_delete_document(self, storage: FilesystemStorage):
        """Deleting a document removes it."""
        storage.create_project("del-project")
        doc = ParsedDocument(
            name="to-delete.txt",
            content="Bye",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("del-project", doc)
        storage.delete_document("del-project", "to-delete.txt")
        assert "to-delete.txt" not in storage.list_documents("del-project")

    def test_load_all_documents(self, storage: FilesystemStorage):
        """Load all documents returns all ParsedDocument objects."""
        storage.create_project("load-project")
        for i in range(3):
            doc = ParsedDocument(
                name=f"doc{i}.txt",
                content=f"Content {i}",
                format="txt",
                metadata={},
                char_count=9,
                parse_warnings=[],
            )
            storage.store_document("load-project", doc)
        docs = storage.load_all_documents("load-project")
        assert len(docs) == 3
        assert all(isinstance(d, ParsedDocument) for d in docs)

    def test_get_nonexistent_document_raises(self, storage: FilesystemStorage):
        """Getting a nonexistent document raises an error."""
        storage.create_project("empty-project")
        with pytest.raises(DocumentNotFoundError):
            storage.get_document("empty-project", "missing.txt")

    def test_store_document_nonexistent_project_raises(self, storage: FilesystemStorage):
        """Storing to a nonexistent project raises an error."""
        doc = ParsedDocument(
            name="orphan.txt",
            content="No home",
            format="txt",
            metadata={},
            char_count=7,
            parse_warnings=[],
        )
        with pytest.raises(ProjectNotFoundError):
            storage.store_document("no-such-project", doc)


class TestPathTraversalProtection:
    """Tests for path traversal protection in storage."""

    def test_project_id_traversal_blocked(self, tmp_path: Path) -> None:
        """Project ID with traversal is blocked."""
        storage = FilesystemStorage(tmp_path)
        with pytest.raises(PathTraversalError):
            storage.create_project("../escape")

    def test_document_name_traversal_blocked(self, tmp_path: Path) -> None:
        """Document name with traversal is blocked."""
        storage = FilesystemStorage(tmp_path)
        storage.create_project("test-project")
        doc = ParsedDocument(
            name="../../etc/passwd",
            content="malicious",
            format="txt",
            metadata={},
            char_count=9,
            parse_warnings=[],
        )
        with pytest.raises(PathTraversalError):
            storage.store_document("test-project", doc)

    def test_raw_file_copy_traversal_blocked(self, tmp_path: Path) -> None:
        """Raw file copy with traversal in doc.name is blocked."""
        storage = FilesystemStorage(tmp_path, keep_raw_files=True)
        storage.create_project("test-project")

        # Create a source file
        source_file = tmp_path / "source.txt"
        source_file.write_text("content")

        doc = ParsedDocument(
            name="../../../escape.txt",
            content="malicious",
            format="txt",
            metadata={},
            char_count=9,
            parse_warnings=[],
        )
        with pytest.raises(PathTraversalError):
            storage.store_document("test-project", doc, raw_path=source_file)

    def test_raw_file_copy_nested_path_works(self, tmp_path: Path) -> None:
        """Raw file copy with nested path (e.g., src/main.py) works."""
        storage = FilesystemStorage(tmp_path, keep_raw_files=True)
        storage.create_project("test-project")

        # Create a source file
        source_file = tmp_path / "source.txt"
        source_file.write_text("content")

        doc = ParsedDocument(
            name="src/main.py",
            content="code",
            format="py",
            metadata={},
            char_count=4,
            parse_warnings=[],
        )
        # Should not raise - nested paths are valid
        storage.store_document("test-project", doc, raw_path=source_file)

        # Verify file was created in correct nested location
        raw_path = tmp_path / "projects" / "test-project" / "raw" / "src" / "main.py"
        assert raw_path.exists()
        assert raw_path.read_text() == "content"


class TestSwapDocs:
    """Tests for swap_docs atomic document replacement."""

    def test_swap_docs_replaces_target_documents(self, storage: FilesystemStorage) -> None:
        """swap_docs replaces target project's docs with source project's docs."""
        storage.create_project("source")
        storage.create_project("target")

        # Add docs to source
        doc_a = ParsedDocument(
            name="new.txt",
            content="new content",
            format="txt",
            metadata={},
            char_count=11,
            parse_warnings=[],
        )
        storage.store_document("source", doc_a)

        # Add different docs to target
        doc_b = ParsedDocument(
            name="old.txt",
            content="old content",
            format="txt",
            metadata={},
            char_count=11,
            parse_warnings=[],
        )
        storage.store_document("target", doc_b)

        storage.swap_docs("source", "target")

        # Target should have source's docs
        docs = storage.list_documents("target")
        assert "new.txt" in docs
        assert "old.txt" not in docs

    def test_swap_docs_restores_on_failure(self, tmp_path: Path) -> None:
        """swap_docs restores target docs if swap fails midway."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("source")
        storage.create_project("target")

        doc = ParsedDocument(
            name="keep.txt",
            content="must survive",
            format="txt",
            metadata={},
            char_count=12,
            parse_warnings=[],
        )
        storage.store_document("target", doc)

        source_doc = ParsedDocument(
            name="new.txt",
            content="new",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("source", source_doc)

        # Make step 2 fail by patching Path.rename to raise on second call
        original_rename = Path.rename
        call_count = [0]

        def failing_rename(self_path, target, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("Disk error")
            return original_rename(self_path, target, *args, **kwargs)

        with patch.object(Path, "rename", failing_rename):
            with pytest.raises(OSError):
                storage.swap_docs("source", "target")

        # Target should still have the original doc
        docs = storage.list_documents("target")
        assert "keep.txt" in docs

    def test_swap_docs_rollback_works_with_stale_backup(self, tmp_path: Path) -> None:
        """swap_docs rollback restores docs correctly when stale backup exists."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("source")
        storage.create_project("target")

        source_doc = ParsedDocument(
            name="new.txt",
            content="new",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("source", source_doc)

        target_doc = ParsedDocument(
            name="keep.txt",
            content="must survive",
            format="txt",
            metadata={},
            char_count=12,
            parse_warnings=[],
        )
        storage.store_document("target", target_doc)

        # Simulate stale backup from a prior crashed swap
        stale_backup = storage._project_path("target") / "docs_backup"
        stale_backup.mkdir()
        (stale_backup / "stale.json").write_text("{}")

        # Make step 2 (rename source→target) fail
        original_rename = Path.rename
        call_count = [0]

        def failing_rename(self_path, target, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("Disk error")
            return original_rename(self_path, target, *args, **kwargs)

        with patch.object(Path, "rename", failing_rename):
            with pytest.raises(OSError):
                storage.swap_docs("source", "target")

        # Rollback must restore original docs correctly
        docs = storage.list_documents("target")
        assert "keep.txt" in docs

    def test_swap_docs_restores_backup_when_target_docs_missing(self, tmp_path: Path) -> None:
        """swap_docs restores docs_backup if target/docs is missing (crash between step 1 and 2)."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("source")
        storage.create_project("target")

        # Store a doc in target, then simulate crash between step 1 and 2:
        # target/docs was moved to docs_backup, but target/docs was never recreated
        target_doc = ParsedDocument(
            name="rescued.txt",
            content="must survive",
            format="txt",
            metadata={},
            char_count=12,
            parse_warnings=[],
        )
        storage.store_document("target", target_doc)

        target_path = storage._project_path("target")
        backup_path = target_path / "docs_backup"
        docs_path = target_path / "docs"

        # Simulate: move docs → docs_backup (step 1 succeeded), then delete docs (step 2 never ran)
        shutil.move(str(docs_path), str(backup_path))
        assert not docs_path.exists()
        assert backup_path.exists()

        # Now store a source doc for the new swap
        source_doc = ParsedDocument(
            name="new.txt",
            content="new",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("source", source_doc)

        # swap_docs should detect the crash state, restore backup, then proceed
        storage.swap_docs("source", "target")

        # Target should have the new source docs
        docs = storage.list_documents("target")
        assert "new.txt" in docs

    def test_swap_docs_succeeds_when_step3_cleanup_fails(self, tmp_path: Path) -> None:
        """swap_docs succeeds even if final backup deletion (step 3) fails."""
        storage = FilesystemStorage(root_path=tmp_path)
        storage.create_project("source")
        storage.create_project("target")

        source_doc = ParsedDocument(
            name="new.txt",
            content="new",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("source", source_doc)

        target_doc = ParsedDocument(
            name="old.txt",
            content="old",
            format="txt",
            metadata={},
            char_count=3,
            parse_warnings=[],
        )
        storage.store_document("target", target_doc)

        def failing_rmtree(path, *args, **kwargs):
            raise OSError("Permission denied")

        with patch("ananta.storage.filesystem.shutil.rmtree", side_effect=failing_rmtree):
            # Should NOT raise despite rmtree failure
            storage.swap_docs("source", "target")

        # Target should have new docs
        docs = storage.list_documents("target")
        assert "new.txt" in docs

    def test_swap_docs_source_not_found_raises(self, storage: FilesystemStorage) -> None:
        """swap_docs raises ProjectNotFoundError when source doesn't exist."""
        storage.create_project("target")

        with pytest.raises(ProjectNotFoundError):
            storage.swap_docs("nonexistent", "target")

    def test_swap_docs_target_not_found_raises(self, storage: FilesystemStorage) -> None:
        """swap_docs raises ProjectNotFoundError when target doesn't exist."""
        storage.create_project("source")

        with pytest.raises(ProjectNotFoundError):
            storage.swap_docs("source", "nonexistent")


class TestTraceOperations:
    """Tests for trace file operations."""

    def test_get_traces_dir_creates_directory(self, storage: FilesystemStorage) -> None:
        """get_traces_dir creates traces directory if needed."""
        storage.create_project("trace-project")
        traces_dir = storage.get_traces_dir("trace-project")
        assert traces_dir.exists()
        assert traces_dir.name == "traces"

    def test_get_traces_dir_nonexistent_project_raises(self, storage: FilesystemStorage) -> None:
        """get_traces_dir raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError):
            storage.get_traces_dir("no-such-project")

    def test_list_traces_empty(self, storage: FilesystemStorage) -> None:
        """list_traces returns empty list when no traces exist."""
        storage.create_project("empty-traces")
        assert storage.list_traces("empty-traces") == []

    def test_list_traces_returns_sorted_by_name(self, storage: FilesystemStorage) -> None:
        """list_traces returns files sorted by name (oldest first)."""
        storage.create_project("sorted-traces")
        traces_dir = storage.get_traces_dir("sorted-traces")
        # Create files with timestamps in names (older first)
        (traces_dir / "2026-02-03T10-00-00-000_aaaa1111.jsonl").write_text("{}")
        (traces_dir / "2026-02-03T10-00-01-000_bbbb2222.jsonl").write_text("{}")
        (traces_dir / "2026-02-03T10-00-02-000_cccc3333.jsonl").write_text("{}")
        traces = storage.list_traces("sorted-traces")
        assert len(traces) == 3
        assert traces[0].name == "2026-02-03T10-00-00-000_aaaa1111.jsonl"
        assert traces[2].name == "2026-02-03T10-00-02-000_cccc3333.jsonl"


class TestGetProjectDir:
    """Tests for get_project_dir method."""

    def test_returns_path_for_existing_project(self, storage: FilesystemStorage) -> None:
        storage.create_project("my-project")
        project_dir = storage.get_project_dir("my-project")
        assert project_dir.exists()
        assert project_dir.name == "my-project"

    def test_raises_for_nonexistent_project(self, storage: FilesystemStorage) -> None:
        with pytest.raises(ProjectNotFoundError):
            storage.get_project_dir("no-such-project")


class TestAnalysisOperations:
    """Tests for analysis CRUD operations."""

    def test_store_and_load_analysis(self, storage: FilesystemStorage) -> None:
        """Storing an analysis allows retrieval."""
        storage.create_project("analysis-project")

        comp = AnalysisComponent(
            name="API",
            path="api/",
            description="REST API",
            apis=[{"type": "rest", "endpoints": ["/health"]}],
            models=["User"],
            entry_points=["api/main.py"],
            internal_dependencies=[],
            auth="JWT",
        )
        dep = AnalysisExternalDep(
            name="Redis",
            type="database",
            description="Cache",
            used_by=["api"],
            optional=True,
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="A test application.",
            components=[comp],
            external_dependencies=[dep],
        )

        storage.store_analysis("analysis-project", analysis)
        loaded = storage.load_analysis("analysis-project")

        assert loaded is not None
        assert loaded.version == "1"
        assert loaded.head_sha == "abc123"
        assert loaded.overview == "A test application."
        assert len(loaded.components) == 1
        assert loaded.components[0].name == "API"
        assert loaded.components[0].auth == "JWT"
        assert len(loaded.external_dependencies) == 1
        assert loaded.external_dependencies[0].optional is True

    def test_load_analysis_without_caveats_uses_default(self, storage: FilesystemStorage) -> None:
        """Loading analysis without caveats key uses dataclass default, not empty string."""
        storage.create_project("no-caveats")
        project_path = storage._project_path("no-caveats")
        analysis_path = project_path / "_analysis.json"
        # Write analysis JSON without the "caveats" key (simulates older format)
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Legacy analysis",
            "components": [],
            "external_dependencies": [],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("no-caveats")
        assert loaded is not None
        assert loaded.caveats != "", "Missing caveats should use dataclass default, not ''"
        assert "AI" in loaded.caveats, "Default caveats should mention AI"

    def test_load_analysis_returns_none_when_missing(self, storage: FilesystemStorage) -> None:
        """Loading analysis returns None when no analysis exists."""
        storage.create_project("no-analysis")
        loaded = storage.load_analysis("no-analysis")
        assert loaded is None

    def test_delete_analysis(self, storage: FilesystemStorage) -> None:
        """Deleting an analysis removes it."""
        storage.create_project("del-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="To delete",
            components=[],
            external_dependencies=[],
        )
        storage.store_analysis("del-analysis", analysis)
        storage.delete_analysis("del-analysis")
        assert storage.load_analysis("del-analysis") is None

    def test_delete_analysis_nonexistent_is_noop(self, storage: FilesystemStorage) -> None:
        """Deleting nonexistent analysis doesn't raise."""
        storage.create_project("empty-analysis")
        storage.delete_analysis("empty-analysis")  # Should not raise

    def test_store_analysis_nonexistent_project_raises(self, storage: FilesystemStorage) -> None:
        """Storing analysis to nonexistent project raises."""
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Orphan",
            components=[],
            external_dependencies=[],
        )
        with pytest.raises(ProjectNotFoundError):
            storage.store_analysis("no-such-project", analysis)

    def test_load_analysis_nonexistent_project_raises(self, storage: FilesystemStorage) -> None:
        """Loading analysis from nonexistent project raises."""
        with pytest.raises(ProjectNotFoundError):
            storage.load_analysis("no-such-project")

    def test_load_analysis_coerces_dict_overview(self, storage: FilesystemStorage) -> None:
        """load_analysis coerces dict overview to string."""
        storage.create_project("bad-types")
        project_path = storage._project_path("bad-types")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": {"summary": "A test app", "details": "more info"},
            "components": [],
            "external_dependencies": [],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-types")
        assert loaded is not None
        assert isinstance(loaded.overview, str)
        assert "summary" in loaded.overview

    def test_load_analysis_coerces_dict_items_in_models(self, storage: FilesystemStorage) -> None:
        """load_analysis coerces dict items in models list to strings."""
        storage.create_project("bad-models")
        project_path = storage._project_path("bad-models")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [
                {
                    "name": "API",
                    "path": "api/",
                    "description": "REST API",
                    "apis": [],
                    "models": [{"name": "User", "fields": ["id"]}, "Session"],
                    "entry_points": ["main.py"],
                    "internal_dependencies": [],
                }
            ],
            "external_dependencies": [],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-models")
        assert loaded is not None
        comp = loaded.components[0]
        assert comp.models == ["User", "Session"]

    def test_load_analysis_coerces_dict_items_in_entry_points(
        self, storage: FilesystemStorage
    ) -> None:
        """load_analysis coerces dict items in entry_points to strings."""
        storage.create_project("bad-eps")
        project_path = storage._project_path("bad-eps")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [
                {
                    "name": "API",
                    "path": "api/",
                    "description": "REST API",
                    "apis": [],
                    "models": [],
                    "entry_points": [{"path": "main.py", "type": "cli"}],
                    "internal_dependencies": [],
                }
            ],
            "external_dependencies": [],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-eps")
        assert loaded is not None
        comp = loaded.components[0]
        assert len(comp.entry_points) == 1
        assert isinstance(comp.entry_points[0], str)

    def test_load_analysis_coerces_dict_items_in_internal_dependencies(
        self, storage: FilesystemStorage
    ) -> None:
        """load_analysis coerces dict items in internal_dependencies."""
        storage.create_project("bad-deps")
        project_path = storage._project_path("bad-deps")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [
                {
                    "name": "API",
                    "path": "api/",
                    "description": "REST API",
                    "apis": [],
                    "models": [],
                    "entry_points": [],
                    "internal_dependencies": [{"name": "db", "version": "1.0"}],
                }
            ],
            "external_dependencies": [],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-deps")
        assert loaded is not None
        comp = loaded.components[0]
        assert comp.internal_dependencies == ["db"]

    def test_load_analysis_coerces_dict_items_in_used_by(self, storage: FilesystemStorage) -> None:
        """load_analysis coerces dict items in used_by to strings."""
        storage.create_project("bad-usedby")
        project_path = storage._project_path("bad-usedby")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [],
            "external_dependencies": [
                {
                    "name": "Redis",
                    "type": "database",
                    "description": "Cache",
                    "used_by": [{"name": "API", "component": "server"}],
                }
            ],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-usedby")
        assert loaded is not None
        dep = loaded.external_dependencies[0]
        assert dep.used_by == ["API"]

    def test_load_analysis_coerces_non_string_component_scalars(
        self, storage: FilesystemStorage
    ) -> None:
        """load_analysis coerces non-string name/path/description in components."""
        storage.create_project("bad-scalars")
        project_path = storage._project_path("bad-scalars")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [
                {
                    "name": 42,
                    "path": None,
                    "description": ["a", "list"],
                    "apis": [],
                    "models": [],
                    "entry_points": [],
                    "internal_dependencies": [],
                }
            ],
            "external_dependencies": [],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-scalars")
        assert loaded is not None
        comp = loaded.components[0]
        assert isinstance(comp.name, str)
        assert isinstance(comp.path, str)
        assert isinstance(comp.description, str)

    def test_load_analysis_coerces_non_string_external_dep_scalars(
        self, storage: FilesystemStorage
    ) -> None:
        """load_analysis coerces non-string name/type/description in external deps."""
        storage.create_project("bad-dep-scalars")
        project_path = storage._project_path("bad-dep-scalars")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [],
            "external_dependencies": [
                {
                    "name": 123,
                    "type": None,
                    "description": {"detail": "a db"},
                    "used_by": [],
                }
            ],
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-dep-scalars")
        assert loaded is not None
        dep = loaded.external_dependencies[0]
        assert isinstance(dep.name, str)
        assert isinstance(dep.type, str)
        assert isinstance(dep.description, str)

    def test_load_analysis_coerces_non_string_caveats(self, storage: FilesystemStorage) -> None:
        """load_analysis coerces non-string caveats to string."""
        storage.create_project("bad-caveats")
        project_path = storage._project_path("bad-caveats")
        analysis_path = project_path / "_analysis.json"
        data = {
            "version": "1",
            "generated_at": "2026-02-06T10:30:00Z",
            "head_sha": "abc123",
            "overview": "Test",
            "components": [],
            "external_dependencies": [],
            "caveats": {"warning": "AI generated"},
        }
        analysis_path.write_text(json.dumps(data))

        loaded = storage.load_analysis("bad-caveats")
        assert loaded is not None
        assert isinstance(loaded.caveats, str)
        assert "AI generated" in loaded.caveats
