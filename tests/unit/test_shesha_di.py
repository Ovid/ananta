"""Tests for Shesha dependency injection support."""

from pathlib import Path
from unittest.mock import MagicMock, create_autospec, patch

from shesha import Shesha
from shesha.parser.registry import ParserRegistry
from shesha.repo.ingester import RepoIngester
from shesha.rlm.engine import RLMEngine
from shesha.storage.base import StorageBackend


def _make_mock_storage() -> MagicMock:
    """Create a mock StorageBackend."""
    mock = create_autospec(StorageBackend, instance=True)
    mock.list_projects.return_value = ["injected-project"]
    mock.project_exists.return_value = True
    mock.list_documents.return_value = []
    return mock


def _make_mock_engine() -> MagicMock:
    """Create a mock RLMEngine."""
    mock = create_autospec(RLMEngine, instance=True)
    mock._pool = None
    return mock


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
        """Shesha uses injected storage for list_projects."""
        mock_storage = _make_mock_storage()
        shesha = Shesha(model="test-model", storage=mock_storage)

        result = shesha.list_projects()

        mock_storage.list_projects.assert_called_once()
        assert result == ["injected-project"]

    def test_injected_storage_used_by_create_project(self, tmp_path: Path):
        """Shesha uses injected storage for create_project."""
        mock_storage = _make_mock_storage()
        shesha = Shesha(model="test-model", storage=mock_storage)

        shesha.create_project("new-proj")

        mock_storage.create_project.assert_called_once_with("new-proj")

    def test_injected_storage_used_by_get_project(self, tmp_path: Path):
        """Shesha uses injected storage for get_project."""
        mock_storage = _make_mock_storage()
        mock_storage.project_exists.return_value = True
        shesha = Shesha(model="test-model", storage=mock_storage)

        project = shesha.get_project("some-proj")

        mock_storage.project_exists.assert_called_once_with("some-proj")
        assert project.project_id == "some-proj"

    def test_injected_storage_used_by_delete_project(self, tmp_path: Path):
        """Shesha uses injected storage for delete_project."""
        mock_storage = _make_mock_storage()
        mock_ingester = _make_mock_ingester(tmp_path)
        mock_ingester.get_source_url.return_value = None
        shesha = Shesha(
            model="test-model",
            storage=mock_storage,
            repo_ingester=mock_ingester,
        )

        shesha.delete_project("to-delete")

        mock_storage.delete_project.assert_called_once_with("to-delete")


class TestEngineInjection:
    """Tests for injecting a custom RLMEngine."""

    def test_injected_engine_used_by_project(self, tmp_path: Path):
        """Project created by Shesha with injected engine uses that engine."""
        mock_storage = _make_mock_storage()
        mock_engine = _make_mock_engine()
        shesha = Shesha(
            model="test-model",
            storage=mock_storage,
            engine=mock_engine,
        )

        project = shesha.create_project("eng-proj")

        assert project._rlm_engine is mock_engine

    def test_start_sets_pool_on_injected_engine(self, tmp_path: Path):
        """start() creates pool and sets it on injected engine via set_pool()."""
        mock_storage = _make_mock_storage()
        mock_engine = _make_mock_engine()
        mock_pool = MagicMock()

        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(
                model="test-model",
                storage=mock_storage,
                engine=mock_engine,
            )

            shesha.start()

            mock_engine.set_pool.assert_called_once_with(mock_pool)


class TestParserRegistryInjection:
    """Tests for injecting a custom ParserRegistry."""

    def test_injected_registry_used_by_create_project(self, tmp_path: Path):
        """Project created by Shesha with injected registry uses that registry."""
        mock_storage = _make_mock_storage()
        custom_registry = _make_mock_registry()
        shesha = Shesha(
            model="test-model",
            storage=mock_storage,
            parser_registry=custom_registry,
        )

        project = shesha.create_project("reg-proj")

        assert project._parser_registry is custom_registry

    def test_register_parser_uses_injected_registry(self, tmp_path: Path):
        """register_parser adds to the injected registry."""
        mock_storage = _make_mock_storage()
        custom_registry = _make_mock_registry()
        shesha = Shesha(
            model="test-model",
            storage=mock_storage,
            parser_registry=custom_registry,
        )

        mock_parser = MagicMock()
        shesha.register_parser(mock_parser)

        assert mock_parser in custom_registry._parsers


class TestRepoIngesterInjection:
    """Tests for injecting a custom RepoIngester."""

    def test_injected_ingester_used_by_delete_project(self, tmp_path: Path):
        """Shesha uses injected repo_ingester for delete_project cleanup."""
        mock_storage = _make_mock_storage()
        mock_ingester = _make_mock_ingester(tmp_path)
        mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
        mock_ingester.is_local_path.return_value = False

        shesha = Shesha(
            model="test-model",
            storage=mock_storage,
            repo_ingester=mock_ingester,
        )

        shesha.delete_project("to-delete")

        mock_ingester.get_source_url.assert_called_once_with("to-delete")
        mock_ingester.delete_repo.assert_called_once_with("to-delete")

    def test_injected_ingester_used_by_get_project_sha(self, tmp_path: Path):
        """Shesha uses injected repo_ingester for get_project_sha."""
        mock_storage = _make_mock_storage()
        mock_ingester = _make_mock_ingester(tmp_path)
        mock_ingester.get_saved_sha.return_value = "abc123"

        shesha = Shesha(
            model="test-model",
            storage=mock_storage,
            repo_ingester=mock_ingester,
        )

        sha = shesha.get_project_sha("some-proj")

        assert sha == "abc123"
        mock_ingester.get_saved_sha.assert_called_once_with("some-proj")


class TestVerifyCitationsWiring:
    """Tests that verify_citations config is passed to RLMEngine."""

    def test_verify_citations_passed_to_engine(self, tmp_path: Path):
        """Shesha passes verify_citations=False from config to engine."""
        from shesha.config import SheshaConfig

        config = SheshaConfig(
            model="test-model", verify_citations=False, storage_path=str(tmp_path)
        )
        shesha = Shesha(config=config)
        assert shesha._rlm_engine.verify_citations is False

    def test_verify_citations_default_true(self, tmp_path: Path):
        """Shesha passes verify_citations=True (default) to engine."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        assert shesha._rlm_engine.verify_citations is True


class TestVerifyWiring:
    """Tests for verify config wiring."""

    def test_verify_passed_to_engine(self, tmp_path: Path) -> None:
        """verify config is passed to RLMEngine."""
        from shesha.config import SheshaConfig

        config = SheshaConfig(model="test-model", verify=True)
        shesha = Shesha(config=config, storage=_make_mock_storage())
        assert shesha._rlm_engine.verify is True

    def test_verify_default_false(self, tmp_path: Path) -> None:
        """verify defaults to False in RLMEngine."""
        from shesha.config import SheshaConfig

        config = SheshaConfig(model="test-model")
        shesha = Shesha(config=config, storage=_make_mock_storage())
        assert shesha._rlm_engine.verify is False


class TestStorageProperty:
    """Tests for Shesha.storage public property."""

    def test_storage_property_returns_storage_backend(self) -> None:
        mock_storage = _make_mock_storage()
        shesha = Shesha(model="test-model", storage=mock_storage)
        assert shesha.storage is mock_storage

    def test_storage_property_returns_default_storage(self, tmp_path: Path) -> None:
        from shesha.storage.filesystem import FilesystemStorage

        shesha = Shesha(model="test-model", storage_path=tmp_path)
        assert isinstance(shesha.storage, FilesystemStorage)


class TestDefaultBehaviorUnchanged:
    """Tests that default behavior works when no DI params are provided."""

    def test_default_creates_filesystem_storage(self, tmp_path: Path):
        """Without DI, Shesha creates FilesystemStorage."""
        from shesha.storage.filesystem import FilesystemStorage

        shesha = Shesha(model="test-model", storage_path=tmp_path)

        assert isinstance(shesha._storage, FilesystemStorage)

    def test_default_creates_rlm_engine(self, tmp_path: Path):
        """Without DI, Shesha creates RLMEngine."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)

        assert isinstance(shesha._rlm_engine, RLMEngine)

    def test_default_creates_parser_registry(self, tmp_path: Path):
        """Without DI, Shesha creates a default parser registry."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)

        assert isinstance(shesha._parser_registry, ParserRegistry)

    def test_default_creates_repo_ingester(self, tmp_path: Path):
        """Without DI, Shesha creates RepoIngester."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)

        assert isinstance(shesha._repo_ingester, RepoIngester)
