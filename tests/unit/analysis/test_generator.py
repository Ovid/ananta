"""Tests for analysis generator."""

from unittest.mock import MagicMock

from shesha.analysis import AnalysisGenerator


class TestAnalysisPromptLoading:
    """Tests for prompt loading."""

    def test_load_prompt_returns_string(self):
        """_load_prompt returns prompt content as string."""
        mock_shesha = MagicMock()
        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)

        prompt = generator._load_prompt("generate")

        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should have substantial content

    def test_load_prompt_contains_json_schema(self):
        """_load_prompt for generate contains JSON schema example."""
        mock_shesha = MagicMock()
        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)

        prompt = generator._load_prompt("generate")

        assert "overview" in prompt
        assert "components" in prompt
        assert "external_dependencies" in prompt


class TestAnalysisGeneratorStructure:
    """Tests for AnalysisGenerator class structure."""

    def test_generator_can_be_imported(self):
        """AnalysisGenerator can be imported from shesha.analysis."""
        assert AnalysisGenerator is not None

    def test_generator_accepts_callables(self):
        """AnalysisGenerator constructor takes get_project and get_project_sha callables."""
        mock_get_project = MagicMock()
        mock_get_sha = MagicMock()
        generator = AnalysisGenerator(
            get_project=mock_get_project,
            get_project_sha=mock_get_sha,
        )

        assert generator._get_project is mock_get_project
        assert generator._get_project_sha is mock_get_sha


class TestAnalysisGeneration:
    """Tests for generate() method."""

    def test_generate_returns_repo_analysis(self):
        """generate() returns a RepoAnalysis object."""
        from shesha.models import RepoAnalysis

        # Mock the shesha instance and project
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        # Mock query result with valid JSON
        mock_result = MagicMock()
        mock_result.answer = """
        ```json
        {
          "overview": "A test application.",
          "components": [
            {
              "name": "API",
              "path": "api/",
              "description": "REST API",
              "apis": [{"type": "rest", "endpoints": ["/health"]}],
              "models": ["User"],
              "entry_points": ["api/main.py"],
              "internal_dependencies": [],
              "auth": null,
              "data_persistence": null
            }
          ],
          "external_dependencies": []
        }
        ```
        """
        mock_project.query.return_value = mock_result

        # Mock repo ingester for SHA
        mock_shesha.get_project_sha.return_value = "abc123def"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        assert isinstance(result, RepoAnalysis)
        assert result.overview == "A test application."
        assert result.head_sha == "abc123def"
        assert result.version == "1"
        assert len(result.components) == 1
        assert result.components[0].name == "API"

    def test_generate_calls_project_query(self):
        """generate() calls project.query with the generate prompt."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = '{"overview": "Test", "components": [], "external_dependencies": []}'
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha123"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        generator.generate("test-project")

        mock_shesha.get_project.assert_called_once_with("test-project")
        mock_project.query.assert_called_once()

        # Verify prompt contains expected content
        call_args = mock_project.query.call_args
        prompt = call_args[0][0]
        assert "overview" in prompt
        assert "components" in prompt

    def test_generate_handles_missing_sha(self):
        """generate() handles missing SHA gracefully."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = '{"overview": "Test", "components": [], "external_dependencies": []}'
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = None

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        assert result.head_sha == ""  # Empty string when no SHA

    def test_generate_coerces_dict_overview_to_string(self):
        """generate() coerces a dict overview from the LLM to a string."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = """
        ```json
        {
          "overview": {"summary": "A web app", "architecture": "MVC"},
          "components": [],
          "external_dependencies": []
        }
        ```
        """
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha789"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        assert isinstance(result.overview, str)
        assert "A web app" in result.overview

    def test_generate_coerces_dict_models_to_strings(self):
        """generate() coerces dict items in models/entry_points/internal_dependencies to strings."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = """
        ```json
        {
          "overview": "Test app",
          "components": [
            {
              "name": "Core",
              "path": "src/",
              "description": "Core module",
              "apis": [],
              "models": [{"name": "User", "fields": ["id", "name"]}],
              "entry_points": [{"file": "main.py", "function": "main"}],
              "internal_dependencies": [{"module": "utils"}]
            }
          ],
          "external_dependencies": []
        }
        ```
        """
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha999"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        comp = result.components[0]
        assert all(isinstance(m, str) for m in comp.models)
        assert all(isinstance(e, str) for e in comp.entry_points)
        assert all(isinstance(d, str) for d in comp.internal_dependencies)

    def test_to_str_list_fallback_uses_json_not_repr(self):
        """coerce_to_str_list fallback produces JSON, not Python repr, for dicts without 'name'."""
        from shesha.models import coerce_to_str_list

        items = [
            "plain_string",
            {"name": "User", "fields": ["id"]},
            {"module": "utils", "version": "1.0"},
        ]
        result = coerce_to_str_list(items)

        assert result[0] == "plain_string"
        assert result[1] == "User"
        # Fallback: dict without "name" key should be JSON (double quotes),
        # not Python repr (single quotes)
        assert '"module"' in result[2]
        assert "'" not in result[2]

    def test_generate_coerces_non_string_component_scalars(self):
        """generate() coerces non-string name/path/description in components."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = """
        ```json
        {
          "overview": "Test",
          "components": [
            {
              "name": 42,
              "path": null,
              "description": ["a", "list"],
              "apis": [],
              "models": [],
              "entry_points": [],
              "internal_dependencies": []
            }
          ],
          "external_dependencies": []
        }
        ```
        """
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha000"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        comp = result.components[0]
        assert isinstance(comp.name, str)
        assert isinstance(comp.path, str)
        assert isinstance(comp.description, str)

    def test_generate_coerces_external_dep_fields(self):
        """generate() coerces non-string fields in external dependencies."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        mock_result = MagicMock()
        mock_result.answer = """
        ```json
        {
          "overview": "Test",
          "components": [],
          "external_dependencies": [
            {
              "name": 123,
              "type": null,
              "description": {"detail": "a db"},
              "used_by": [{"name": "API"}, "Frontend"],
              "optional": false
            }
          ]
        }
        ```
        """
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha111"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        dep = result.external_dependencies[0]
        assert isinstance(dep.name, str)
        assert isinstance(dep.type, str)
        assert isinstance(dep.description, str)
        assert all(isinstance(u, str) for u in dep.used_by)

    def test_generate_handles_invalid_json(self):
        """generate() falls back to raw answer when JSON extraction fails."""
        mock_shesha = MagicMock()
        mock_project = MagicMock()
        mock_shesha.get_project.return_value = mock_project

        # Response with no valid JSON - just plain text
        mock_result = MagicMock()
        mock_result.answer = "This is a plain text response with no JSON."
        mock_project.query.return_value = mock_result
        mock_shesha.get_project_sha.return_value = "sha456"

        generator = AnalysisGenerator(get_project=mock_shesha.get_project, get_project_sha=mock_shesha.get_project_sha)
        result = generator.generate("test-project")

        # Fallback: raw answer becomes overview, empty components/deps
        assert result.overview == "This is a plain text response with no JSON."
        assert result.components == []
        assert result.external_dependencies == []
