"""Tests for main Shesha class."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shesha import Shesha
from shesha.exceptions import ProjectNotFoundError, RepoError, RepoIngestError
from shesha.models import RepoProjectResult
from shesha.repo.ingester import IngestResult
from shesha.storage.filesystem import FilesystemStorage


@pytest.fixture
def shesha_instance(tmp_path: Path) -> Shesha:
    """Create a Shesha instance for testing (no Docker needed at init)."""
    return Shesha(model="test-model", storage_path=tmp_path)


class TestDockerAvailability:
    """Tests for Docker availability check at start() time."""

    def test_init_does_not_check_docker(self, tmp_path: Path):
        """Shesha.__init__ does not check Docker availability.

        Construction should succeed without Docker for ingest-only workflows.
        """
        from docker.errors import DockerException

        with patch("shesha.shesha.docker") as mock_docker:
            mock_docker.from_env.side_effect = DockerException("Connection refused")

            # Should NOT raise — Docker check is deferred to start()
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            assert shesha is not None

    def test_init_does_not_create_container_pool(self, tmp_path: Path):
        """Shesha.__init__ defers ContainerPool creation to start()."""
        with patch("shesha.shesha.ContainerPool") as mock_pool_cls:
            Shesha(model="test-model", storage_path=tmp_path)
            mock_pool_cls.assert_not_called()

    def test_start_checks_docker_and_creates_pool(self, tmp_path: Path):
        """start() checks Docker and creates the container pool."""
        from shesha.sandbox.pool import ContainerPool

        mock_pool = MagicMock(spec=ContainerPool)
        with (
            patch("shesha.shesha.docker") as mock_docker,
            patch("shesha.shesha.ContainerPool", return_value=mock_pool) as mock_pool_cls,
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            # Before start: no Docker check, no pool
            mock_docker.from_env.assert_not_called()
            mock_pool_cls.assert_not_called()

            shesha.start()

            # After start: Docker checked, pool created and started
            mock_docker.from_env.assert_called_once()
            mock_pool_cls.assert_called_once()
            mock_pool.start.assert_called_once()

    def test_start_raises_clear_error_when_docker_not_running(self, tmp_path: Path):
        """start() raises clear error when Docker is not running."""
        from docker.errors import DockerException

        with patch("shesha.shesha.docker") as mock_docker:
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            mock_docker.from_env.side_effect = DockerException(
                "Error while fetching server API version: "
                "('Connection aborted.', ConnectionRefusedError(61, 'Connection refused'))"
            )

            with pytest.raises(RuntimeError) as exc_info:
                shesha.start()

            error_msg = str(exc_info.value)
            assert "Docker" in error_msg
            assert "not running" in error_msg or "start" in error_msg.lower()

    def test_start_raises_helpful_error_when_socket_not_found(self, tmp_path: Path):
        """start() raises helpful error mentioning Podman when socket not found."""
        from docker.errors import DockerException

        with patch("shesha.shesha.docker") as mock_docker:
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            mock_docker.from_env.side_effect = DockerException(
                "Error while fetching server API version: "
                "('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))"
            )

            with pytest.raises(RuntimeError) as exc_info:
                shesha.start()

            error_msg = str(exc_info.value)
            assert "DOCKER_HOST" in error_msg
            assert "Podman" in error_msg or "podman" in error_msg

    def test_init_registers_atexit_cleanup(self, tmp_path: Path):
        """__init__ registers an atexit handler that calls stop()."""
        with patch("shesha.shesha.atexit") as mock_atexit:
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            mock_atexit.register.assert_called_once()

            # The registered function should call stop() on the instance
            cleanup_fn = mock_atexit.register.call_args[0][0]
            with patch.object(shesha, "stop") as mock_stop:
                cleanup_fn()
                mock_stop.assert_called_once()

    def test_stop_clears_pool_on_engine(self, tmp_path: Path):
        """stop() clears the pool reference on the engine for defensive cleanup."""
        from shesha.sandbox.pool import ContainerPool

        mock_pool = MagicMock(spec=ContainerPool)
        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.start()

            with patch.object(shesha.rlm_engine, "set_pool") as mock_set:
                shesha.stop()
                mock_set.assert_called_once_with(None)

    def test_stop_without_start_is_safe(self, tmp_path: Path):
        """stop() works safely even if start() was never called (no pool)."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        # Should not raise
        shesha.stop()

    def test_start_is_idempotent(self, tmp_path: Path):
        """Calling start() twice creates only one pool."""
        from shesha.sandbox.pool import ContainerPool

        with (
            patch("shesha.shesha.docker"),
            patch(
                "shesha.shesha.ContainerPool",
                return_value=MagicMock(spec=ContainerPool),
            ) as mock_pool_cls,
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.start()
            shesha.start()

            mock_pool_cls.assert_called_once()

    def test_start_sets_pool_on_engine(self, tmp_path: Path):
        """start() sets the pool on the RLM engine via set_pool()."""
        mock_pool = MagicMock()
        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with patch.object(shesha.rlm_engine, "set_pool") as mock_set:
                shesha.start()
                mock_set.assert_called_once_with(mock_pool)

    def test_start_starts_pool_before_publishing_to_engine(self, tmp_path: Path):
        """start() calls pool.start() before set_pool() so a failed start
        doesn't leave the engine holding a broken pool reference."""
        from shesha.sandbox.pool import ContainerPool

        mock_pool = MagicMock(spec=ContainerPool)
        call_order: list[str] = []
        mock_pool.start.side_effect = lambda: call_order.append("pool.start")

        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            original_set_pool = shesha.rlm_engine.set_pool

            def tracked_set_pool(pool):
                call_order.append("set_pool")
                original_set_pool(pool)

            with patch.object(shesha.rlm_engine, "set_pool", side_effect=tracked_set_pool):
                shesha.start()

        assert call_order == ["pool.start", "set_pool"]

    def test_stop_clears_engine_pool_before_stopping(self, tmp_path: Path):
        """stop() clears engine pool reference before pool.stop() so in-flight
        queries see pool=None rather than a stopped pool."""
        from shesha.sandbox.pool import ContainerPool

        mock_pool = MagicMock(spec=ContainerPool)
        call_order: list[str] = []
        mock_pool.stop.side_effect = lambda: call_order.append("pool.stop")

        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)
            shesha.start()
            original_set_pool = shesha.rlm_engine.set_pool

            def tracked_set_pool(pool):
                call_order.append(f"set_pool({pool})")
                original_set_pool(pool)

            with patch.object(shesha.rlm_engine, "set_pool", side_effect=tracked_set_pool):
                shesha.stop()

        assert call_order == ["set_pool(None)", "pool.stop"]


class TestShesha:
    """Tests for Shesha class."""

    def test_create_project(self, tmp_path: Path):
        """Creating a project returns a Project instance."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        project = shesha.create_project("my-project")

        assert project.project_id == "my-project"

    def test_list_projects(self, tmp_path: Path):
        """List projects returns project IDs."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        shesha.create_project("project-a")
        shesha.create_project("project-b")

        projects = shesha.list_projects()
        assert "project-a" in projects
        assert "project-b" in projects

    def test_get_project(self, tmp_path: Path):
        """Get project returns existing project."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        shesha.create_project("existing")

        project = shesha.get_project("existing")
        assert project.project_id == "existing"

    def test_delete_project(self, tmp_path: Path):
        """Delete project removes it."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)
        shesha.create_project("to-delete")
        shesha.delete_project("to-delete")

        assert "to-delete" not in shesha.list_projects()

    def test_register_parser(self, tmp_path: Path):
        """Register custom parser adds it to the registry."""
        shesha = Shesha(model="test-model", storage_path=tmp_path)

        # Create a mock custom parser
        mock_parser = MagicMock()
        mock_parser.can_parse.return_value = True

        shesha.register_parser(mock_parser)

        # The parser should now be findable through the public API.
        # Use a file extension no built-in parser handles so it matches
        # our mock (whose can_parse returns True for everything).
        assert shesha.parser_registry.find_parser(Path("test.xyz123")) is mock_parser

    def test_stop_after_restart_stops_pool(self, tmp_path: Path):
        """Stop after start-stop-start cycle should stop the pool."""
        from shesha.sandbox.pool import ContainerPool

        mock_pool = MagicMock(spec=ContainerPool)
        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            # First cycle: start then stop
            shesha.start()
            shesha.stop()

            # Second cycle: start again
            shesha.start()

            # Reset call count to track second stop
            mock_pool.stop.reset_mock()

            # Second stop should call pool.stop()
            shesha.stop()

            mock_pool.stop.assert_called_once()

    def test_shesha_passes_pool_to_engine_on_start(self, tmp_path: Path):
        """Shesha passes pool to RLMEngine via set_pool() when start() is called."""
        mock_pool = MagicMock()
        with (
            patch("shesha.shesha.docker"),
            patch("shesha.shesha.ContainerPool", return_value=mock_pool),
        ):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with patch.object(shesha.rlm_engine, "set_pool") as mock_set:
                shesha.start()
                mock_set.assert_called_once_with(mock_pool)

    def test_shesha_uses_config_load_by_default(self, tmp_path: Path):
        """Shesha uses SheshaConfig.load() by default, picking up env vars."""
        import os
        from unittest.mock import patch as mock_patch

        with mock_patch.dict(os.environ, {"SHESHA_MAX_ITERATIONS": "99"}):
            shesha = Shesha(storage_path=tmp_path)
            assert shesha._config.max_iterations == 99

    def test_delete_project_cleans_up_remote_repo(self, tmp_path: Path):
        """delete_project removes cloned repo for remote projects by default."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("to-delete")

                shesha.delete_project("to-delete")

                mock_ingester.delete_repo.assert_called_once_with("to-delete")

    def test_delete_project_skips_cleanup_for_local_repo(self, tmp_path: Path):
        """delete_project does not call delete_repo for local repos."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/path/to/local/repo"
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("local-project")

                shesha.delete_project("local-project")

                mock_ingester.delete_repo.assert_not_called()

    def test_delete_project_respects_cleanup_repo_false(self, tmp_path: Path):
        """delete_project skips repo cleanup when cleanup_repo=False."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("to-delete")

                shesha.delete_project("to-delete", cleanup_repo=False)

                mock_ingester.delete_repo.assert_not_called()


class TestCreateProjectFromRepo:
    """Tests for create_project_from_repo method."""

    def test_creates_new_project(self, tmp_path: Path):
        """create_project_from_repo creates project for new repo."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                # ingest() creates the project and returns result
                def fake_ingest(**kwargs):
                    shesha.storage.create_project("my-project")
                    return IngestResult(files_ingested=1)

                mock_ingester.ingest.side_effect = fake_ingest

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="my-project",
                )

                assert isinstance(result, RepoProjectResult)
                assert result.status == "created"
                assert result.project.project_id == "my-project"

    def test_unchanged_when_sha_matches(self, tmp_path: Path):
        """create_project_from_repo returns unchanged when SHAs match."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "abc123"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_unchanged_when_both_shas_none(self, tmp_path: Path):
        """When both saved and remote SHAs are None, treat as unchanged."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_remote_sha.return_value = None
                mock_ingester.get_saved_path.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_check_failed_when_remote_sha_is_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """When saved_sha exists but remote SHA is None (network failure),
        return check_failed instead of updates_available."""
        import logging

        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                with caplog.at_level(logging.WARNING, logger="shesha.shesha"):
                    result = shesha.create_project_from_repo(
                        url="https://github.com/org/repo",
                        name="my-project",
                    )

                assert result.status == "check_failed"
                assert any("Could not determine current SHA" in r.message for r in caplog.records)

    def test_unchanged_when_saved_sha_none_but_current_sha_valid(self, tmp_path: Path):
        """When saved_sha is None (e.g. SHA save failed during initial ingest)
        but current_sha is valid, treat as unchanged — not false updates_available."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_remote_sha.return_value = "abc123"
                mock_ingester.get_saved_path.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_updates_available_when_sha_differs(self, tmp_path: Path):
        """create_project_from_repo returns updates_available when SHAs differ."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "updates_available"

    def test_apply_updates_skips_pull_for_local_repos(self, tmp_path: Path):
        """apply_updates() should not call pull() for local repositories."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Simulate a local repo with updates available
                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_sha_from_path.return_value = "def456"  # Different SHA
                mock_ingester.list_files_from_path.return_value = []
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("local-project")

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="local-project",
                )

                assert result.status == "updates_available"

                # Apply updates
                mock_ingester.pull.reset_mock()
                result.apply_updates()

                # pull() should NOT be called for local repos
                mock_ingester.pull.assert_not_called()

    def test_saves_source_url_for_local_repo(self, tmp_path: Path):
        """create_project_from_repo delegates to ingest() which saves source URL."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                def fake_ingest(**kwargs):
                    shesha.storage.create_project("my-project")
                    return IngestResult(files_ingested=0)

                mock_ingester.ingest.side_effect = fake_ingest

                shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="my-project",
                )

                # ingest() is called with the right URL
                mock_ingester.ingest.assert_called_once()
                call_kwargs = mock_ingester.ingest.call_args[1]
                assert call_kwargs["url"] == "/path/to/local/repo"
                assert call_kwargs["name"] == "my-project"

    def test_saves_resolved_source_url_for_relative_local_path(self, tmp_path: Path):
        """create_project_from_repo passes relative URL to ingest() for resolution."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                def fake_ingest(**kwargs):
                    shesha.storage.create_project("my-project")
                    return IngestResult(files_ingested=0)

                mock_ingester.ingest.side_effect = fake_ingest

                shesha.create_project_from_repo(
                    url="./myrepo",
                    name="my-project",
                )

                # URL is passed through to ingest()
                call_kwargs = mock_ingester.ingest.call_args[1]
                assert call_kwargs["url"] == "./myrepo"

    def test_raises_for_non_git_local_path(self, tmp_path: Path):
        """create_project_from_repo raises RepoIngestError for non-git local dirs."""
        from shesha.exceptions import RepoIngestError

        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError) as exc_info:
                    shesha.create_project_from_repo(
                        url="/path/to/non-git-dir",
                        name="my-project",
                    )

                assert "not a git repository" in str(exc_info.value).lower()


class TestAtomicIngestion:
    """Tests for atomic repo ingestion (stage-then-swap for updates, cleanup on failure)."""

    def test_failed_new_project_ingestion_propagates_error(self, tmp_path: Path):
        """Failed ingestion propagates error from ingest()."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"
                mock_ingester.ingest.side_effect = RepoIngestError(
                    "/path/to/local/repo", cause=OSError("disk full")
                )

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError):
                    shesha.create_project_from_repo(
                        url="/path/to/local/repo",
                        name="clean-on-fail",
                    )

    def test_failed_update_propagates_error(self, tmp_path: Path):
        """Failed update propagates error from ingest()."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("update-project")

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="update-project",
                )

                assert result.status == "updates_available"

                mock_ingester.ingest.side_effect = RepoIngestError(
                    "/path/to/local/repo", cause=OSError("disk full")
                )

                with pytest.raises(RepoIngestError):
                    result.apply_updates()

    def test_successful_update_wraps_ingest_result(self, tmp_path: Path):
        """Successful update wraps IngestResult into RepoProjectResult."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("orphan-project")

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="orphan-project",
                )

                assert result.status == "updates_available"

                mock_ingester.ingest.return_value = IngestResult(
                    files_ingested=2, files_skipped=1, warnings=["skipped binary"]
                )

                updated = result.apply_updates()

                assert updated.status == "updated"
                assert updated.files_ingested == 2
                assert updated.files_skipped == 1
                assert updated.warnings == ["skipped binary"]

    def test_staging_name_does_not_collide_with_user_project(self, tmp_path: Path):
        """Staging project name must not collide with existing user projects."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.list_files_from_path.return_value = ["file.py"]
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                # Create a user project whose name matches the old staging pattern
                shesha.storage.create_project("_staging_my-project")

                from shesha.models import ParsedDocument

                original_doc = ParsedDocument(
                    name="original.txt",
                    content="original",
                    format="txt",
                    metadata={},
                    char_count=8,
                    parse_warnings=[],
                )
                shesha.storage.store_document("my-project", original_doc)

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="my-project",
                )

                assert result.status == "updates_available"

                with patch.object(shesha.parser_registry, "find_parser") as mock_find:
                    mock_parser = MagicMock()
                    mock_parser.parse.return_value = MagicMock(
                        name="file.py",
                        content="new",
                        format="py",
                        metadata={},
                        char_count=3,
                        parse_warnings=[],
                    )
                    mock_find.return_value = mock_parser

                    result.apply_updates()

                # The user's unrelated project must still exist
                assert shesha.storage.project_exists("_staging_my-project")

    def test_update_passes_custom_storage_to_ingest(self, tmp_path: Path):
        """Updates pass the custom storage backend to ingest()."""
        from shesha.storage.base import StorageBackend

        real_storage = FilesystemStorage(root_path=tmp_path)

        class CustomStorage:
            """Wrapper that delegates to FilesystemStorage but isn't one."""

            def __init__(self, inner: FilesystemStorage):
                self._inner = inner

            def __getattr__(self, name: str) -> object:
                return getattr(self._inner, name)

        custom: StorageBackend = CustomStorage(real_storage)  # type: ignore[assignment]

        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path, storage=custom)
                real_storage.create_project("custom-project")

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="custom-project",
                )

                assert result.status == "updates_available"

                mock_ingester.ingest.return_value = IngestResult(files_ingested=1)

                result.apply_updates()

                # Verify ingest was called with the custom storage
                call_kwargs = mock_ingester.ingest.call_args[1]
                assert call_kwargs["storage"] is custom

    def test_ingest_receives_is_update_flag(self, tmp_path: Path):
        """apply_updates passes is_update=True to ingest()."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("flag-project")

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="flag-project",
                )

                assert result.status == "updates_available"

                mock_ingester.ingest.return_value = IngestResult(files_ingested=1)

                result.apply_updates()

                call_kwargs = mock_ingester.ingest.call_args[1]
                assert call_kwargs["is_update"] is True


class TestIngestRepoErrorHandling:
    """Tests for _ingest_repo error propagation from RepoIngester.ingest()."""

    def test_ingest_result_warnings_propagated(self, tmp_path: Path):
        """Warnings from ingest() are propagated to RepoProjectResult."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                def fake_ingest(**kwargs):
                    shesha.storage.create_project("parse-err-project")
                    return IngestResult(
                        files_ingested=0,
                        files_skipped=1,
                        warnings=["Failed to parse bad.py: syntax error"],
                    )

                mock_ingester.ingest.side_effect = fake_ingest

                result = shesha.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="parse-err-project",
                )

                assert result.files_skipped == 1
                assert any("bad.py" in w for w in result.warnings)

    def test_unexpected_error_propagates_from_ingest(self, tmp_path: Path):
        """RepoIngestError from ingest() propagates through _ingest_repo."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"
                mock_ingester.ingest.side_effect = RepoIngestError(
                    "/path/to/local/repo", cause=OSError("disk full")
                )

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError) as exc_info:
                    shesha.create_project_from_repo(
                        url="/path/to/local/repo",
                        name="crash-project",
                    )

                assert isinstance(exc_info.value.__cause__, OSError)

    def test_failed_new_remote_project_error_from_ingest(self, tmp_path: Path):
        """Failed ingestion of a new remote project propagates from ingest()."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.repos_dir = tmp_path / "repos"
                mock_ingester.ingest.side_effect = RepoIngestError(
                    "https://github.com/org/repo", cause=OSError("disk full")
                )

                shesha = Shesha(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError):
                    shesha.create_project_from_repo(
                        url="https://github.com/org/repo",
                        name="remote-project",
                    )


class TestCheckRepoForUpdates:
    """Tests for check_repo_for_updates method."""

    def test_returns_unchanged_when_no_updates(self, tmp_path: Path):
        """check_repo_for_updates returns unchanged when repo is current."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Cloned repo with matching SHAs
                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "abc123"
                mock_ingester.resolve_token.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "unchanged"
                assert result.project.project_id == "my-project"

    def test_returns_updates_available_when_sha_differs(self, tmp_path: Path):
        """check_repo_for_updates returns updates_available when SHAs differ."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Cloned repo with different SHAs
                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"
                mock_ingester.resolve_token.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "updates_available"

    def test_returns_unchanged_when_both_shas_none(self, tmp_path: Path):
        """Both SHAs None should return unchanged, not false updates_available."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_remote_sha.return_value = None
                mock_ingester.resolve_token.return_value = None
                mock_ingester.get_saved_path.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "unchanged"

    def test_raises_when_project_not_found(self, tmp_path: Path):
        """check_repo_for_updates raises ProjectNotFoundError for non-existent project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with pytest.raises(ProjectNotFoundError) as exc_info:
                shesha.check_repo_for_updates("nonexistent")

            assert "does not exist" in str(exc_info.value)

    def test_raises_when_no_repo_url(self, tmp_path: Path):
        """check_repo_for_updates raises RepoError when no repo URL stored."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # No repo URL stored (not a cloned repo)
                mock_ingester.get_source_url.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                with pytest.raises(RepoError) as exc_info:
                    shesha.check_repo_for_updates("my-project")

                assert "No repository URL" in str(exc_info.value)

    def test_works_with_local_repo(self, tmp_path: Path):
        """check_repo_for_updates works with local repos using get_source_url."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Local repo - get_repo_url returns None (no cloned dir)
                # but get_source_url returns the local path
                mock_ingester.get_source_url.return_value = "/path/to/local/repo"
                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_sha_from_path.return_value = "abc123"
                mock_ingester.resolve_token.return_value = None

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "unchanged"
                assert result.project.project_id == "my-project"
                # Verify it used get_source_url, not get_repo_url
                mock_ingester.get_source_url.assert_called_once_with("my-project")

    def test_loads_saved_path_for_subdirectory_scoped_project(self, tmp_path: Path):
        """check_repo_for_updates loads saved path and passes it through."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"
                mock_ingester.resolve_token.return_value = None
                mock_ingester.get_saved_path.return_value = "src/"

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                result = shesha.check_repo_for_updates("my-project")

                assert result.status == "updates_available"
                # The apply_updates closure must use the saved path
                # We verify by checking _handle_existing_project received it
                mock_ingester.get_saved_path.assert_called_once_with("my-project")


class TestGetProjectInfo:
    """Tests for get_project_info method."""

    def test_returns_info_for_remote_repo(self, tmp_path: Path):
        """get_project_info returns correct info for remote repo project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("my-project")

                info = shesha.get_project_info("my-project")

                assert info.project_id == "my-project"
                assert info.source_url == "https://github.com/org/repo"
                assert info.is_local is False
                assert info.source_exists is True

    def test_returns_info_for_existing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=True when local path exists."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                local_path = tmp_path / "local_repo"
                local_path.mkdir()

                mock_ingester.get_source_url.return_value = str(local_path)
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("local-project")

                info = shesha.get_project_info("local-project")

                assert info.is_local is True
                assert info.source_exists is True

    def test_returns_info_for_missing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=False when local path missing."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/nonexistent/path"
                mock_ingester.is_local_path.return_value = True

                shesha = Shesha(model="test-model", storage_path=tmp_path)
                shesha.storage.create_project("missing-project")

                info = shesha.get_project_info("missing-project")

                assert info.is_local is True
                assert info.source_exists is False

    def test_raises_for_nonexistent_project(self, tmp_path: Path):
        """get_project_info raises ProjectNotFoundError for non-existent project."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            shesha = Shesha(model="test-model", storage_path=tmp_path)

            with pytest.raises(ProjectNotFoundError) as exc_info:
                shesha.get_project_info("nonexistent")

            assert "does not exist" in str(exc_info.value)


class TestExtractRepoName:
    """Tests for _extract_repo_name method."""

    def _make_shesha(self, tmp_path: Path, is_local: bool = False) -> Shesha:
        """Create a Shesha instance with mocked Docker and RepoIngester."""
        with patch("shesha.shesha.docker"), patch("shesha.shesha.ContainerPool"):
            with patch("shesha.shesha.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester
                mock_ingester.is_local_path.return_value = is_local
                shesha = Shesha(model="test-model", storage_path=tmp_path)
        return shesha

    def test_https_url(self, tmp_path: Path):
        """Standard HTTPS GitHub URL extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha") == "Ovid-shesha"

    def test_https_url_trailing_slash(self, tmp_path: Path):
        """HTTPS URL with trailing slash extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha/") == "Ovid-shesha"

    def test_https_url_dot_git(self, tmp_path: Path):
        """HTTPS URL with .git suffix extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha.git") == "Ovid-shesha"

    def test_https_url_dot_git_trailing_slash(self, tmp_path: Path):
        """HTTPS URL with .git and trailing slash extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://github.com/Ovid/shesha.git/") == "Ovid-shesha"

    def test_ssh_url(self, tmp_path: Path):
        """SSH git URL extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("git@github.com:Ovid/shesha.git") == "Ovid-shesha"

    def test_gitlab_url(self, tmp_path: Path):
        """GitLab URL extracts org-repo name."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("https://gitlab.com/myorg/myrepo") == "myorg-myrepo"

    def test_local_path_uses_parent_and_name(self, tmp_path: Path):
        """Local path extracts parent-name to avoid collisions."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        assert shesha._extract_repo_name("/home/user/projects/shesha") == "projects-shesha"

    def test_local_home_relative_path(self, tmp_path: Path):
        """Home-relative local path extracts parent-name."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        assert shesha._extract_repo_name("~/projects/myrepo") == "projects-myrepo"

    def test_local_path_trailing_slash(self, tmp_path: Path):
        """Local path with trailing slash extracts parent-name."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        assert shesha._extract_repo_name("/home/user/projects/shesha/") == "projects-shesha"

    def test_local_relative_path_no_leading_dash(self, tmp_path: Path):
        """Relative local path without parent resolves to avoid leading dash."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        result = shesha._extract_repo_name("myrepo")
        assert not result.startswith("-"), f"Name should not start with dash: {result}"
        assert result.endswith("myrepo")

    def test_local_dot_relative_path(self, tmp_path: Path):
        """Dot-relative local path resolves to meaningful parent-name."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        result = shesha._extract_repo_name("./myrepo")
        assert not result.startswith("-"), f"Name should not start with dash: {result}"
        assert not result.startswith("."), f"Name should not start with dot: {result}"
        assert result.endswith("myrepo")

    def test_local_path_with_spaces_sanitized(self, tmp_path: Path):
        """Local path with spaces produces a safe slug without spaces."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        result = shesha._extract_repo_name("/home/user/my projects/my repo")
        assert " " not in result
        assert re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", result), (
            f"Result {result!r} does not match _SAFE_ID_RE"
        )

    @pytest.mark.parametrize(
        "raw",
        [".hidden", "_private", "...dots", "___underscores"],
    )
    def test_sanitize_strips_leading_non_alphanumeric(self, raw: str):
        """_sanitize_project_id output must start with [a-zA-Z0-9]."""
        result = Shesha._sanitize_project_id(raw)
        assert re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", result), (
            f"_sanitize_project_id({raw!r}) = {result!r} does not match _SAFE_ID_RE"
        )

    def test_local_hidden_dir_produces_safe_id(self, tmp_path: Path):
        """Local path under a hidden directory produces a _SAFE_ID_RE-valid ID."""
        shesha = self._make_shesha(tmp_path, is_local=True)
        result = shesha._extract_repo_name("/home/user/.config/.repo")
        assert re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", result), (
            f"Result {result!r} does not match _SAFE_ID_RE"
        )

    def test_fallback_for_unparseable_url(self, tmp_path: Path):
        """Unparseable URL falls back to unnamed-repo."""
        shesha = self._make_shesha(tmp_path)
        assert shesha._extract_repo_name("not-a-url") == "unnamed-repo"


class TestGetProjectInfoWithAnalysis:
    """Tests for get_project_info including analysis_status."""

    def test_get_project_info_includes_analysis_status(self, shesha_instance):
        """get_project_info includes analysis_status field."""
        shesha_instance.create_project("info-with-status")

        info = shesha_instance.get_project_info("info-with-status")

        assert info.analysis_status == "missing"  # No analysis yet

    def test_get_project_info_analysis_status_current(self, shesha_instance):
        """get_project_info shows 'current' when analysis matches SHA."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("info-current")
        shesha_instance.repo_ingester.save_sha("info-current", "sha123")
        shesha_instance.repo_ingester.save_source_url("info-current", "/fake")

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="sha123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance.storage.store_analysis("info-current", analysis)

        info = shesha_instance.get_project_info("info-current")

        assert info.analysis_status == "current"

    def test_get_project_info_analysis_status_stale(self, shesha_instance):
        """get_project_info shows 'stale' when analysis SHA differs from current."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("info-stale")
        shesha_instance.repo_ingester.save_sha("info-stale", "new_sha")
        shesha_instance.repo_ingester.save_source_url("info-stale", "/fake")

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="old_sha",  # Different from saved SHA
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance.storage.store_analysis("info-stale", analysis)

        info = shesha_instance.get_project_info("info-stale")

        assert info.analysis_status == "stale"


class TestAnalysisStatus:
    """Tests for analysis status checking."""

    def test_get_analysis_status_missing(self, shesha_instance: Shesha, tmp_path: Path):
        """get_analysis_status returns 'missing' when no analysis exists."""
        shesha_instance.create_project("no-analysis-project")
        status = shesha_instance.get_analysis_status("no-analysis-project")
        assert status == "missing"

    def test_get_analysis_status_current(self, shesha_instance: Shesha, tmp_path: Path):
        """get_analysis_status returns 'current' when analysis matches HEAD."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("current-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance.storage.store_analysis("current-analysis", analysis)
        shesha_instance.repo_ingester.save_sha("current-analysis", "abc123")
        shesha_instance.repo_ingester.save_source_url("current-analysis", "/fake/path")

        status = shesha_instance.get_analysis_status("current-analysis")
        assert status == "current"

    def test_get_analysis_status_stale(self, shesha_instance: Shesha, tmp_path: Path):
        """get_analysis_status returns 'stale' when analysis SHA differs from HEAD."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("stale-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="old_sha_123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        shesha_instance.storage.store_analysis("stale-analysis", analysis)
        shesha_instance.repo_ingester.save_sha("stale-analysis", "new_sha_456")
        shesha_instance.repo_ingester.save_source_url("stale-analysis", "/fake/path")

        status = shesha_instance.get_analysis_status("stale-analysis")
        assert status == "stale"

    def test_get_analysis_status_nonexistent_project_raises(self, shesha_instance: Shesha):
        """get_analysis_status raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError, match="does not exist"):
            shesha_instance.get_analysis_status("no-such-project")


class TestGetAnalysis:
    """Tests for get_analysis method."""

    def test_get_analysis_returns_stored_analysis(self, shesha_instance: Shesha):
        """get_analysis returns the stored analysis."""
        from shesha.models import AnalysisComponent, RepoAnalysis

        shesha_instance.create_project("get-analysis-project")
        comp = AnalysisComponent(
            name="API",
            path="api/",
            description="REST API",
            apis=[],
            models=["User"],
            entry_points=["main.py"],
            internal_dependencies=[],
        )
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test app",
            components=[comp],
            external_dependencies=[],
        )
        shesha_instance.storage.store_analysis("get-analysis-project", analysis)

        result = shesha_instance.get_analysis("get-analysis-project")
        assert result is not None
        assert result.overview == "Test app"
        assert len(result.components) == 1

    def test_get_analysis_returns_none_when_missing(self, shesha_instance: Shesha):
        """get_analysis returns None when no analysis exists."""
        shesha_instance.create_project("no-analysis")
        result = shesha_instance.get_analysis("no-analysis")
        assert result is None

    def test_get_analysis_nonexistent_project_raises(self, shesha_instance: Shesha):
        """get_analysis raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError, match="does not exist"):
            shesha_instance.get_analysis("no-such-project")


class TestGenerateAnalysis:
    """Tests for generate_analysis method."""

    def test_generate_analysis_stores_result(self, shesha_instance):
        """generate_analysis stores the generated analysis."""
        from shesha.models import RepoAnalysis

        # Create a project
        shesha_instance.create_project("gen-analysis")
        shesha_instance.repo_ingester.save_sha("gen-analysis", "sha123")

        # Mock the generator
        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="sha123",
            overview="Generated analysis",
            components=[],
            external_dependencies=[],
        )

        with patch("shesha.shesha.AnalysisGenerator") as mock_generator:
            mock_generator.return_value.generate.return_value = mock_analysis

            result = shesha_instance.generate_analysis("gen-analysis")

            assert result.overview == "Generated analysis"
            # Verify it was stored
            stored = shesha_instance.storage.load_analysis("gen-analysis")
            assert stored is not None
            assert stored.overview == "Generated analysis"

    def test_generate_analysis_returns_analysis(self, shesha_instance):
        """generate_analysis returns the generated RepoAnalysis."""
        from shesha.models import RepoAnalysis

        shesha_instance.create_project("return-analysis")

        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc",
            overview="Test",
            components=[],
            external_dependencies=[],
        )

        with patch("shesha.shesha.AnalysisGenerator") as mock_generator:
            mock_generator.return_value.generate.return_value = mock_analysis

            result = shesha_instance.generate_analysis("return-analysis")

            assert isinstance(result, RepoAnalysis)
            assert result.overview == "Test"

    def test_generate_analysis_nonexistent_project_raises(self, shesha_instance):
        """generate_analysis raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError, match="does not exist"):
            shesha_instance.generate_analysis("no-such-project")
