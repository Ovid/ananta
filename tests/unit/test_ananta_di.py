"""Tests for Ananta dependency injection support."""

from pathlib import Path
from unittest.mock import MagicMock, create_autospec, patch

from ananta import Ananta
from ananta.parser.registry import ParserRegistry
from ananta.repo.ingester import RepoIngester
from ananta.rlm.engine import RLMEngine
from ananta.storage.base import StorageBackend


def _make_mock_storage() -> MagicMock:
    """Create a mock StorageBackend."""
    mock = create_autospec(StorageBackend, instance=True)
    mock.list_projects.return_value = ["injected-project"]
    mock.project_exists.return_value = True
    mock.list_documents.return_value = []
    return mock


def _make_mock_engine() -> MagicMock:
    """Create a mock RLMEngine."""
    return create_autospec(RLMEngine, instance=True)


def _make_mock_registry() -> ParserRegistry:
    """Create a real ParserRegistry (no need to mock — it's simple)."""
    return ParserRegistry()


def _make_mock_ingester(tmp_path: Path) -> MagicMock:
    """Create a mock RepoIngester."""
    mock = create_autospec(RepoIngester, instance=True)
    mock.repos_dir = tmp_path / "repos"
    return mock


class TestStorageInjection:
    """Tests for injecting a custom StorageBackend."""

    def test_injected_storage_used_by_list_projects(self, tmp_path: Path):
        """Ananta uses injected storage for list_projects."""
        mock_storage = _make_mock_storage()
        ananta = Ananta(model="test-model", storage=mock_storage)

        result = ananta.list_projects()

        mock_storage.list_projects.assert_called_once()
        assert result == ["injected-project"]

    def test_injected_storage_used_by_create_project(self, tmp_path: Path):
        """Ananta uses injected storage for create_project."""
        mock_storage = _make_mock_storage()
        ananta = Ananta(model="test-model", storage=mock_storage)

        ananta.create_project("new-proj")

        mock_storage.create_project.assert_called_once_with("new-proj")

    def test_injected_storage_used_by_get_project(self, tmp_path: Path):
        """Ananta uses injected storage for get_project."""
        mock_storage = _make_mock_storage()
        mock_storage.project_exists.return_value = True
        ananta = Ananta(model="test-model", storage=mock_storage)

        project = ananta.get_project("some-proj")

        mock_storage.project_exists.assert_called_once_with("some-proj")
        assert project.project_id == "some-proj"

    def test_injected_storage_used_by_delete_project(self, tmp_path: Path):
        """Ananta uses injected storage for delete_project."""
        mock_storage = _make_mock_storage()
        mock_ingester = _make_mock_ingester(tmp_path)
        mock_ingester.get_source_url.return_value = None
        ananta = Ananta(
            model="test-model",
            storage=mock_storage,
            repo_ingester=mock_ingester,
        )

        ananta.delete_project("to-delete")

        mock_storage.delete_project.assert_called_once_with("to-delete")


class TestEngineInjection:
    """Tests for injecting a custom RLMEngine."""

    def test_injected_engine_used_by_project(self, tmp_path: Path):
        """Project created by Ananta with injected engine uses that engine."""
        mock_storage = _make_mock_storage()
        mock_engine = _make_mock_engine()
        ananta = Ananta(
            model="test-model",
            storage=mock_storage,
            engine=mock_engine,
        )

        project = ananta.create_project("eng-proj")

        assert project.rlm_engine is mock_engine

    def test_start_sets_pool_on_injected_engine(self, tmp_path: Path):
        """start() creates pool and sets it on injected engine via set_pool()."""
        mock_storage = _make_mock_storage()
        mock_engine = _make_mock_engine()
        mock_pool = MagicMock()

        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(
                model="test-model",
                storage=mock_storage,
                engine=mock_engine,
            )

            ananta.start()

            mock_engine.set_pool.assert_called_once_with(mock_pool)


class TestParserRegistryInjection:
    """Tests for injecting a custom ParserRegistry."""

    def test_injected_registry_used_by_create_project(self, tmp_path: Path):
        """Project created by Ananta with injected registry uses that registry."""
        mock_storage = _make_mock_storage()
        custom_registry = _make_mock_registry()
        ananta = Ananta(
            model="test-model",
            storage=mock_storage,
            parser_registry=custom_registry,
        )

        project = ananta.create_project("reg-proj")

        assert project.parser_registry is custom_registry

    def test_register_parser_uses_injected_registry(self, tmp_path: Path):
        """register_parser adds to the injected registry."""
        mock_storage = _make_mock_storage()
        custom_registry = _make_mock_registry()
        ananta = Ananta(
            model="test-model",
            storage=mock_storage,
            parser_registry=custom_registry,
        )

        mock_parser = MagicMock()
        mock_parser.can_parse.return_value = True
        ananta.register_parser(mock_parser)

        # Verify the parser was registered by checking behavioral output
        assert custom_registry.find_parser(Path("test.txt")) is mock_parser


class TestRepoIngesterInjection:
    """Tests for injecting a custom RepoIngester."""

    def test_injected_ingester_used_by_delete_project(self, tmp_path: Path):
        """Ananta uses injected repo_ingester for delete_project cleanup."""
        mock_storage = _make_mock_storage()
        mock_ingester = _make_mock_ingester(tmp_path)
        mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
        mock_ingester.is_local_path.return_value = False

        ananta = Ananta(
            model="test-model",
            storage=mock_storage,
            repo_ingester=mock_ingester,
        )

        ananta.delete_project("to-delete")

        mock_ingester.get_source_url.assert_called_once_with("to-delete")
        mock_ingester.delete_repo.assert_called_once_with("to-delete")

    def test_injected_ingester_used_by_get_project_sha(self, tmp_path: Path):
        """Ananta uses injected repo_ingester for get_project_sha."""
        mock_storage = _make_mock_storage()
        mock_ingester = _make_mock_ingester(tmp_path)
        mock_ingester.get_saved_sha.return_value = "abc123"

        ananta = Ananta(
            model="test-model",
            storage=mock_storage,
            repo_ingester=mock_ingester,
        )

        sha = ananta.get_project_sha("some-proj")

        assert sha == "abc123"
        mock_ingester.get_saved_sha.assert_called_once_with("some-proj")


class TestVerifyCitationsWiring:
    """Tests that verify_citations config is passed to RLMEngine."""

    def test_verify_citations_passed_to_engine(self, tmp_path: Path):
        """Ananta passes verify_citations=False from config to engine."""
        from ananta.config import AnantaConfig

        config = AnantaConfig(
            model="test-model", verify_citations=False, storage_path=str(tmp_path)
        )
        ananta = Ananta(config=config)
        assert ananta.rlm_engine.verify_citations is False

    def test_verify_citations_default_true(self, tmp_path: Path):
        """Ananta passes verify_citations=True (default) to engine."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        assert ananta.rlm_engine.verify_citations is True


class TestVerifyWiring:
    """Tests for verify config wiring."""

    def test_verify_passed_to_engine(self, tmp_path: Path) -> None:
        """verify config is passed to RLMEngine."""
        from ananta.config import AnantaConfig

        config = AnantaConfig(model="test-model", verify=True)
        ananta = Ananta(config=config, storage=_make_mock_storage())
        assert ananta.rlm_engine.verify is True

    def test_verify_default_false(self, tmp_path: Path) -> None:
        """verify defaults to False in RLMEngine."""
        from ananta.config import AnantaConfig

        config = AnantaConfig(model="test-model")
        ananta = Ananta(config=config, storage=_make_mock_storage())
        assert ananta.rlm_engine.verify is False


class TestStorageProperty:
    """Tests for Ananta.storage public property."""

    def test_storage_property_returns_storage_backend(self) -> None:
        mock_storage = _make_mock_storage()
        ananta = Ananta(model="test-model", storage=mock_storage)
        assert ananta.storage is mock_storage

    def test_storage_property_returns_default_storage(self, tmp_path: Path) -> None:
        from ananta.storage.filesystem import FilesystemStorage

        ananta = Ananta(model="test-model", storage_path=tmp_path)
        assert isinstance(ananta.storage, FilesystemStorage)


class TestDefaultBehaviorUnchanged:
    """Tests that default behavior works when no DI params are provided."""

    def test_default_creates_filesystem_storage(self, tmp_path: Path):
        """Without DI, Ananta creates FilesystemStorage."""
        from ananta.storage.filesystem import FilesystemStorage

        ananta = Ananta(model="test-model", storage_path=tmp_path)

        assert isinstance(ananta.storage, FilesystemStorage)

    def test_default_creates_rlm_engine(self, tmp_path: Path):
        """Without DI, Ananta creates RLMEngine."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)

        assert isinstance(ananta.rlm_engine, RLMEngine)

    def test_default_creates_parser_registry(self, tmp_path: Path):
        """Without DI, Ananta creates a default parser registry."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)

        assert isinstance(ananta.parser_registry, ParserRegistry)

    def test_default_creates_repo_ingester(self, tmp_path: Path):
        """Without DI, Ananta creates RepoIngester."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)

        assert isinstance(ananta.repo_ingester, RepoIngester)
