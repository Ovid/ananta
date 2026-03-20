"""Tests for data models."""

from unittest.mock import MagicMock

import pytest

from ananta.models import (
    AnalysisComponent,
    AnalysisExternalDep,
    ProjectInfo,
    QueryContext,
    RepoAnalysis,
    RepoProjectResult,
)


class TestProjectInfo:
    """Tests for ProjectInfo dataclass."""

    def test_project_info_dataclass(self):
        """ProjectInfo stores project metadata correctly."""
        info = ProjectInfo(
            project_id="my-project",
            source_url="https://github.com/org/repo",
            is_local=False,
            source_exists=True,
        )

        assert info.project_id == "my-project"
        assert info.source_url == "https://github.com/org/repo"
        assert info.is_local is False
        assert info.source_exists is True

    def test_project_info_with_none_source(self):
        """ProjectInfo handles None source_url for non-repo projects."""
        info = ProjectInfo(
            project_id="manual-project",
            source_url=None,
            is_local=False,
            source_exists=True,
        )

        assert info.source_url is None


class TestRepoProjectResult:
    """Tests for RepoProjectResult dataclass."""

    def test_created_status(self):
        """RepoProjectResult can be created with 'created' status."""
        mock_project = MagicMock()
        result = RepoProjectResult(
            project=mock_project,
            status="created",
            files_ingested=10,
            files_skipped=2,
            warnings=["some warning"],
        )

        assert result.project is mock_project
        assert result.status == "created"
        assert result.files_ingested == 10
        assert result.files_skipped == 2
        assert result.warnings == ["some warning"]

    def test_default_values(self):
        """RepoProjectResult has correct defaults for optional fields."""
        mock_project = MagicMock()
        result = RepoProjectResult(
            project=mock_project,
            status="created",
            files_ingested=5,
        )

        assert result.files_skipped == 0
        assert result.warnings == []

    def test_unchanged_status(self):
        """RepoProjectResult can be created with 'unchanged' status."""
        result = RepoProjectResult(
            project=MagicMock(),
            status="unchanged",
            files_ingested=0,
        )
        assert result.status == "unchanged"

    def test_updates_available_status(self):
        """RepoProjectResult can be created with 'updates_available' status."""
        result = RepoProjectResult(
            project=MagicMock(),
            status="updates_available",
            files_ingested=10,
        )
        assert result.status == "updates_available"

    def test_apply_updates_stores_callback(self):
        """RepoProjectResult stores apply_updates callback."""
        mock_project = MagicMock()
        callback_called = []

        def mock_callback():
            callback_called.append(True)
            return RepoProjectResult(
                project=mock_project,
                status="created",
                files_ingested=15,
            )

        result = RepoProjectResult(
            project=mock_project,
            status="updates_available",
            files_ingested=10,
            _apply_updates_fn=mock_callback,
        )

        updated = result.apply_updates()
        assert callback_called == [True]
        assert updated.files_ingested == 15

    def test_apply_updates_raises_when_unchanged(self):
        """apply_updates raises ValueError when status is not 'updates_available'."""
        mock_project = MagicMock()
        result = RepoProjectResult(
            project=mock_project,
            status="unchanged",
            files_ingested=10,
        )

        with pytest.raises(ValueError, match="only valid when status is 'updates_available'"):
            result.apply_updates()


class TestQueryContext:
    """Tests for QueryContext dataclass."""

    def test_query_context_stores_metadata(self) -> None:
        """QueryContext stores all query metadata."""
        ctx = QueryContext(
            trace_id="abc123",
            question="What is X?",
            document_ids=["doc1", "doc2"],
            model="claude-sonnet-4-20250514",
            system_prompt="You are an assistant...",
            subcall_prompt="Analyze this...",
        )
        assert ctx.trace_id == "abc123"
        assert ctx.question == "What is X?"
        assert ctx.document_ids == ["doc1", "doc2"]
        assert ctx.model == "claude-sonnet-4-20250514"
        assert ctx.system_prompt == "You are an assistant..."
        assert ctx.subcall_prompt == "Analyze this..."


class TestAnalysisComponent:
    """Tests for AnalysisComponent dataclass."""

    def test_analysis_component_required_fields(self):
        """AnalysisComponent stores required fields correctly."""
        comp = AnalysisComponent(
            name="Server API",
            path="server/",
            description="FastAPI service for chat",
            apis=[{"type": "rest", "endpoints": ["/api/chat"]}],
            models=["ChatSession", "Message"],
            entry_points=["server/main.py"],
            internal_dependencies=["ai_layer"],
        )

        assert comp.name == "Server API"
        assert comp.path == "server/"
        assert comp.description == "FastAPI service for chat"
        assert comp.apis == [{"type": "rest", "endpoints": ["/api/chat"]}]
        assert comp.models == ["ChatSession", "Message"]
        assert comp.entry_points == ["server/main.py"]
        assert comp.internal_dependencies == ["ai_layer"]

    def test_analysis_component_optional_fields(self):
        """AnalysisComponent has optional auth and data_persistence."""
        comp = AnalysisComponent(
            name="Web",
            path="web/",
            description="Frontend",
            apis=[],
            models=[],
            entry_points=[],
            internal_dependencies=[],
            auth="Cognito JWT",
            data_persistence="LocalStorage",
        )

        assert comp.auth == "Cognito JWT"
        assert comp.data_persistence == "LocalStorage"

    def test_analysis_component_defaults_none_for_optional(self):
        """AnalysisComponent defaults optional fields to None."""
        comp = AnalysisComponent(
            name="Simple",
            path="simple/",
            description="Simple component",
            apis=[],
            models=[],
            entry_points=[],
            internal_dependencies=[],
        )

        assert comp.auth is None
        assert comp.data_persistence is None


class TestAnalysisExternalDep:
    """Tests for AnalysisExternalDep dataclass."""

    def test_external_dep_required_fields(self):
        """AnalysisExternalDep stores required fields correctly."""
        dep = AnalysisExternalDep(
            name="Amazon Bedrock",
            type="ai_service",
            description="Claude model for agent invocations",
            used_by=["ai_layer"],
        )

        assert dep.name == "Amazon Bedrock"
        assert dep.type == "ai_service"
        assert dep.description == "Claude model for agent invocations"
        assert dep.used_by == ["ai_layer"]

    def test_external_dep_optional_defaults_false(self):
        """AnalysisExternalDep defaults optional to False."""
        dep = AnalysisExternalDep(
            name="PostgreSQL",
            type="database",
            description="Main database",
            used_by=["server"],
        )

        assert dep.optional is False

    def test_external_dep_optional_true(self):
        """AnalysisExternalDep can set optional to True."""
        dep = AnalysisExternalDep(
            name="Atlassian API",
            type="external_api",
            description="Jira/Confluence integration",
            used_by=["ai_layer"],
            optional=True,
        )

        assert dep.optional is True


class TestProjectInfoAnalysisStatus:
    """Tests for ProjectInfo.analysis_status field."""

    def test_project_info_with_analysis_status(self):
        """ProjectInfo can include analysis_status."""
        info = ProjectInfo(
            project_id="my-project",
            source_url="https://github.com/org/repo",
            is_local=False,
            source_exists=True,
            analysis_status="current",
        )

        assert info.analysis_status == "current"

    def test_project_info_analysis_status_defaults_none(self):
        """ProjectInfo.analysis_status defaults to None."""
        info = ProjectInfo(
            project_id="my-project",
            source_url=None,
            is_local=False,
            source_exists=True,
        )

        assert info.analysis_status is None


class TestRepoAnalysis:
    """Tests for RepoAnalysis dataclass."""

    def test_repo_analysis_all_fields(self):
        """RepoAnalysis stores all fields correctly."""
        from ananta.models import AnalysisComponent, AnalysisExternalDep, RepoAnalysis

        comp = AnalysisComponent(
            name="API",
            path="api/",
            description="REST API",
            apis=[],
            models=[],
            entry_points=[],
            internal_dependencies=[],
        )
        dep = AnalysisExternalDep(
            name="Redis",
            type="database",
            description="Cache",
            used_by=["api"],
        )

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123def456",
            overview="A sample application.",
            components=[comp],
            external_dependencies=[dep],
        )

        assert analysis.version == "1"
        assert analysis.generated_at == "2026-02-06T10:30:00Z"
        assert analysis.head_sha == "abc123def456"
        assert analysis.overview == "A sample application."
        assert len(analysis.components) == 1
        assert analysis.components[0].name == "API"
        assert len(analysis.external_dependencies) == 1
        assert analysis.external_dependencies[0].name == "Redis"

    def test_repo_analysis_default_caveats(self):
        """RepoAnalysis has default caveats message."""
        from ananta.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )

        assert "AI" in analysis.caveats
        assert "incorrect" in analysis.caveats

    def test_repo_analysis_custom_caveats(self):
        """RepoAnalysis can have custom caveats."""
        from ananta.models import RepoAnalysis

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
            caveats="Custom warning.",
        )

        assert analysis.caveats == "Custom warning."


class TestAnalysisComponentTypeValidation:
    """Tests for AnalysisComponent __post_init__ type validation."""

    def test_dict_name_raises_type_error(self) -> None:
        """Dict name should raise TypeError."""
        with pytest.raises(TypeError, match="name"):
            AnalysisComponent(
                name={"key": "value"},  # type: ignore[arg-type]
                path="api/",
                description="REST API",
                apis=[],
                models=[],
                entry_points=[],
                internal_dependencies=[],
            )

    def test_dict_path_raises_type_error(self) -> None:
        """Dict path should raise TypeError."""
        with pytest.raises(TypeError, match="path"):
            AnalysisComponent(
                name="API",
                path={"key": "value"},  # type: ignore[arg-type]
                description="REST API",
                apis=[],
                models=[],
                entry_points=[],
                internal_dependencies=[],
            )

    def test_dict_description_raises_type_error(self) -> None:
        """Dict description should raise TypeError."""
        with pytest.raises(TypeError, match="description"):
            AnalysisComponent(
                name="API",
                path="api/",
                description={"key": "value"},  # type: ignore[arg-type]
                apis=[],
                models=[],
                entry_points=[],
                internal_dependencies=[],
            )

    def test_dict_items_in_models_raises_type_error(self) -> None:
        """Dict items in models list should raise TypeError."""
        with pytest.raises(TypeError, match="models"):
            AnalysisComponent(
                name="API",
                path="api/",
                description="REST API",
                apis=[],
                models=[{"name": "User"}],  # type: ignore[list-item]
                entry_points=[],
                internal_dependencies=[],
            )

    def test_dict_items_in_entry_points_raises_type_error(self) -> None:
        """Dict items in entry_points list should raise TypeError."""
        with pytest.raises(TypeError, match="entry_points"):
            AnalysisComponent(
                name="API",
                path="api/",
                description="REST API",
                apis=[],
                models=[],
                entry_points=[{"path": "main.py"}],  # type: ignore[list-item]
                internal_dependencies=[],
            )

    def test_dict_items_in_internal_dependencies_raises_type_error(self) -> None:
        """Dict items in internal_dependencies should raise TypeError."""
        with pytest.raises(TypeError, match="internal_dependencies"):
            AnalysisComponent(
                name="API",
                path="api/",
                description="REST API",
                apis=[],
                models=[],
                entry_points=[],
                internal_dependencies=[{"name": "db"}],  # type: ignore[list-item]
            )


class TestAnalysisExternalDepTypeValidation:
    """Tests for AnalysisExternalDep __post_init__ type validation."""

    def test_dict_name_raises_type_error(self) -> None:
        """Dict name should raise TypeError."""
        with pytest.raises(TypeError, match="name"):
            AnalysisExternalDep(
                name={"key": "value"},  # type: ignore[arg-type]
                type="database",
                description="Cache",
                used_by=["API"],
            )

    def test_dict_description_raises_type_error(self) -> None:
        """Dict description should raise TypeError."""
        with pytest.raises(TypeError, match="description"):
            AnalysisExternalDep(
                name="Redis",
                type="database",
                description={"key": "value"},  # type: ignore[arg-type]
                used_by=["API"],
            )

    def test_dict_items_in_used_by_raises_type_error(self) -> None:
        """Dict items in used_by should raise TypeError."""
        with pytest.raises(TypeError, match="used_by"):
            AnalysisExternalDep(
                name="Redis",
                type="database",
                description="Cache",
                used_by=[{"name": "API"}],  # type: ignore[list-item]
            )


class TestRepoAnalysisTypeValidation:
    """Tests for RepoAnalysis __post_init__ type validation."""

    def test_dict_overview_raises_type_error(self) -> None:
        """Dict overview should raise TypeError."""
        with pytest.raises(TypeError, match="overview"):
            RepoAnalysis(
                version="1",
                generated_at="2026-02-06T10:30:00Z",
                head_sha="abc123",
                overview={"summary": "test"},  # type: ignore[arg-type]
                components=[],
                external_dependencies=[],
            )

    def test_dict_caveats_raises_type_error(self) -> None:
        """Dict caveats should raise TypeError."""
        with pytest.raises(TypeError, match="caveats"):
            RepoAnalysis(
                version="1",
                generated_at="2026-02-06T10:30:00Z",
                head_sha="abc123",
                overview="Test",
                components=[],
                external_dependencies=[],
                caveats={"note": "caveat"},  # type: ignore[arg-type]
            )


class TestCoercionHelpers:
    """Tests for coerce_to_str and coerce_to_str_list."""

    def test_coerce_to_str_with_string(self) -> None:
        """String input returns unchanged."""
        from ananta.models import coerce_to_str

        assert coerce_to_str("hello") == "hello"

    def test_coerce_to_str_with_dict(self) -> None:
        """Dict input returns JSON-encoded string."""
        from ananta.models import coerce_to_str

        result = coerce_to_str({"key": "value"})
        assert isinstance(result, str)
        assert "key" in result

    def test_coerce_to_str_with_list(self) -> None:
        """List input returns JSON-encoded string."""
        from ananta.models import coerce_to_str

        result = coerce_to_str(["a", "b"])
        assert isinstance(result, str)

    def test_coerce_to_str_list_with_strings(self) -> None:
        """String items pass through unchanged."""
        from ananta.models import coerce_to_str_list

        assert coerce_to_str_list(["a", "b"]) == ["a", "b"]

    def test_coerce_to_str_list_with_dict_name_key(self) -> None:
        """Dict items with 'name' key use the name value."""
        from ananta.models import coerce_to_str_list

        result = coerce_to_str_list([{"name": "User", "fields": ["id"]}])
        assert result == ["User"]

    def test_coerce_to_str_list_with_dict_no_name_key(self) -> None:
        """Dict items without 'name' key are JSON-encoded."""
        from ananta.models import coerce_to_str_list

        result = coerce_to_str_list([{"path": "/api", "method": "GET"}])
        assert len(result) == 1
        assert isinstance(result[0], str)
        assert "path" in result[0]

    def test_coerce_to_str_list_mixed(self) -> None:
        """Mixed list with strings and dicts."""
        from ananta.models import coerce_to_str_list

        result = coerce_to_str_list(["User", {"name": "Session"}, {"path": "/api"}])
        assert result[0] == "User"
        assert result[1] == "Session"
        assert isinstance(result[2], str)

    def test_coerce_to_str_list_with_non_string_name_value(self) -> None:
        """Dict with 'name' key whose value is not a string is coerced."""
        from ananta.models import coerce_to_str_list

        result = coerce_to_str_list([{"name": 42}, {"name": ["a", "b"]}])
        assert all(isinstance(r, str) for r in result)
        assert result[0] == "42"
        assert result[1] == '["a", "b"]'
