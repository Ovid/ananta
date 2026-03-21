"""Tests for main Ananta class."""

import logging
import os
import re
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import DockerException

from ananta import Ananta
from ananta.exceptions import ProjectNotFoundError, RepoError, RepoIngestError
from ananta.models import AnalysisComponent, ParsedDocument, RepoAnalysis, RepoProjectResult
from ananta.repo.ingester import IngestResult
from ananta.sandbox.pool import ContainerPool
from ananta.storage.base import StorageBackend
from ananta.storage.filesystem import FilesystemStorage


@pytest.fixture
def ananta_instance(tmp_path: Path) -> Ananta:
    """Create an Ananta instance for testing (no Docker needed at init)."""
    return Ananta(model="test-model", storage_path=tmp_path)


class TestDockerAvailability:
    """Tests for Docker availability check at start() time."""

    def test_init_does_not_check_docker(self, tmp_path: Path):
        """Ananta.__init__ does not check Docker availability.

        Construction should succeed without Docker for ingest-only workflows.
        """

        with patch("ananta.ananta.docker") as mock_docker:
            mock_docker.from_env.side_effect = DockerException("Connection refused")

            # Should NOT raise — Docker check is deferred to start()
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            assert ananta is not None

    def test_init_does_not_create_container_pool(self, tmp_path: Path):
        """Ananta.__init__ defers ContainerPool creation to start()."""
        with patch("ananta.ananta.ContainerPool") as mock_pool_cls:
            Ananta(model="test-model", storage_path=tmp_path)
            mock_pool_cls.assert_not_called()

    def test_start_checks_docker_and_creates_pool(self, tmp_path: Path):
        """start() checks Docker and creates the container pool."""
        mock_pool = MagicMock(spec=ContainerPool)
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch("ananta.ananta.ContainerPool", return_value=mock_pool) as mock_pool_cls,
            patch.dict(os.environ, {"DOCKER_HOST": "unix:///var/run/docker.sock"}),
        ):
            mock_docker.from_env.return_value = MagicMock()
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            mock_docker.from_env.assert_not_called()
            mock_pool_cls.assert_not_called()

            ananta.start()

            mock_docker.from_env.assert_called_once()
            mock_pool_cls.assert_called_once()
            mock_pool.start.assert_called_once()

    def test_start_raises_clear_error_when_docker_not_running(self, tmp_path: Path):
        """start() raises clear error when Docker is not running."""
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch.dict(os.environ, {"DOCKER_HOST": "unix:///var/run/docker.sock"}),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            mock_docker.from_env.side_effect = DockerException(
                "Error while fetching server API version: "
                "('Connection aborted.', ConnectionRefusedError(61, 'Connection refused'))"
            )

            with pytest.raises(RuntimeError) as exc_info:
                ananta.start()

            error_msg = str(exc_info.value)
            assert "not responding" in error_msg

    def test_start_raises_helpful_error_when_socket_not_found(self, tmp_path: Path):
        """start() raises helpful error mentioning Podman when no socket found."""
        with (
            patch("ananta.ananta.docker"),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", []),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError) as exc_info:
                ananta.start()

            error_msg = str(exc_info.value)
            assert "DOCKER_HOST" in error_msg
            assert "Podman" in error_msg or "podman" in error_msg

    def test_init_registers_atexit_cleanup(self, tmp_path: Path):
        """__init__ registers an atexit handler that calls stop()."""
        with patch("ananta.ananta.atexit") as mock_atexit:
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            mock_atexit.register.assert_called_once()

            # The registered function should call stop() on the instance
            cleanup_fn = mock_atexit.register.call_args[0][0]
            with patch.object(ananta, "stop") as mock_stop:
                cleanup_fn()
                mock_stop.assert_called_once()

    def test_stop_clears_pool_on_engine(self, tmp_path: Path):
        """stop() clears the pool reference on the engine for defensive cleanup."""

        mock_pool = MagicMock(spec=ContainerPool)
        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()

            with patch.object(ananta.rlm_engine, "set_pool") as mock_set:
                ananta.stop()
                mock_set.assert_called_once_with(None)

    def test_stop_without_start_is_safe(self, tmp_path: Path):
        """stop() works safely even if start() was never called (no pool)."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        # Should not raise
        ananta.stop()

    def test_start_retries_after_pool_start_failure(self, tmp_path: Path):
        """If pool.start() raises, subsequent start() should retry, not return early."""

        call_count = 0

        def failing_then_succeeding_start():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Docker error")

        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.start.side_effect = failing_then_succeeding_start

        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError, match="Docker error"):
                ananta.start()

            # Second call should retry, not return early
            ananta.start()
            assert call_count == 2

    def test_start_cleans_up_pool_on_partial_failure(self, tmp_path: Path):
        """If pool.start() raises, pool.stop() must be called to avoid orphaned containers."""
        mock_pool = MagicMock(spec=ContainerPool)
        mock_pool.start.side_effect = RuntimeError("third container failed")

        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError, match="third container failed"):
                ananta.start()

            mock_pool.stop.assert_called_once()

    def test_start_is_idempotent(self, tmp_path: Path):
        """Calling start() twice creates only one pool."""

        with (
            patch("ananta.ananta.docker"),
            patch(
                "ananta.ananta.ContainerPool",
                return_value=MagicMock(spec=ContainerPool),
            ) as mock_pool_cls,
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()
            ananta.start()

            mock_pool_cls.assert_called_once()

    def test_start_sets_pool_on_engine(self, tmp_path: Path):
        """start() sets the pool on the RLM engine via set_pool()."""
        mock_pool = MagicMock()
        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with patch.object(ananta.rlm_engine, "set_pool") as mock_set:
                ananta.start()
                mock_set.assert_called_once_with(mock_pool)

    def test_start_starts_pool_before_publishing_to_engine(self, tmp_path: Path):
        """start() calls pool.start() before set_pool() so a failed start
        doesn't leave the engine holding a broken pool reference."""

        mock_pool = MagicMock(spec=ContainerPool)
        call_order: list[str] = []
        mock_pool.start.side_effect = lambda: call_order.append("pool.start")

        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            original_set_pool = ananta.rlm_engine.set_pool

            def tracked_set_pool(pool):
                call_order.append("set_pool")
                original_set_pool(pool)

            with patch.object(ananta.rlm_engine, "set_pool", side_effect=tracked_set_pool):
                ananta.start()

        assert call_order == ["pool.start", "set_pool"]

    def test_stop_clears_engine_pool_before_stopping(self, tmp_path: Path):
        """stop() clears engine pool reference before pool.stop() so in-flight
        queries see pool=None rather than a stopped pool."""

        mock_pool = MagicMock(spec=ContainerPool)
        call_order: list[str] = []
        mock_pool.stop.side_effect = lambda: call_order.append("pool.stop")

        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()
            original_set_pool = ananta.rlm_engine.set_pool

            def tracked_set_pool(pool):
                call_order.append(f"set_pool({pool})")
                original_set_pool(pool)

            with patch.object(ananta.rlm_engine, "set_pool", side_effect=tracked_set_pool):
                ananta.stop()

        assert call_order == ["set_pool(None)", "pool.stop"]

    def test_check_docker_uses_context_inspect_when_no_docker_host(self, tmp_path: Path):
        """When DOCKER_HOST is not set, discovery tries docker context inspect."""
        mock_client = MagicMock()
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch("ananta.ananta.ContainerPool", return_value=MagicMock(spec=ContainerPool)),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run") as mock_run,
            patch("ananta.ananta.Path.is_socket", return_value=False),
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="unix:///Users/test/.docker/run/docker.sock\n",
            )
            mock_docker.from_env.return_value = mock_client
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()

            mock_docker.from_env.assert_called_once()

    def test_check_docker_respects_existing_docker_host(self, tmp_path: Path):
        """When DOCKER_HOST is set, discovery is skipped and from_env() is used directly."""
        mock_client = MagicMock()
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch("ananta.ananta.ContainerPool", return_value=MagicMock(spec=ContainerPool)),
            patch.dict(os.environ, {"DOCKER_HOST": "unix:///custom/docker.sock"}),
        ):
            mock_docker.from_env.return_value = mock_client
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()

            mock_docker.from_env.assert_called_once()
            mock_client.close.assert_called_once()

    def test_check_docker_falls_through_when_docker_cli_not_installed(self, tmp_path: Path):
        """When docker CLI is not installed, discovery silently falls through to path probing."""
        mock_client = MagicMock()
        sock_path = tmp_path / "docker.sock"
        sock_path.touch()  # Will mock is_socket

        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch("ananta.ananta.ContainerPool", return_value=MagicMock(spec=ContainerPool)),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [sock_path]),
            patch.object(Path, "is_socket", return_value=True),
        ):
            mock_docker.from_env.return_value = mock_client
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()

            mock_docker.from_env.assert_called_once()
            mock_client.close.assert_called_once()

    def test_check_docker_falls_through_when_context_returns_nonzero(self, tmp_path: Path):
        """When docker context inspect returns non-zero, discovery falls through."""
        mock_client = MagicMock()
        sock_path = tmp_path / "docker.sock"
        sock_path.touch()

        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch("ananta.ananta.ContainerPool", return_value=MagicMock(spec=ContainerPool)),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run") as mock_run,
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [sock_path]),
            patch.object(Path, "is_socket", return_value=True),
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            mock_docker.from_env.return_value = mock_client
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()

            mock_docker.from_env.assert_called_once()

    def test_check_docker_falls_through_when_context_returns_garbage(self, tmp_path: Path):
        """When docker context inspect returns success but invalid scheme, falls through."""
        mock_client = MagicMock()
        sock_path = tmp_path / "docker.sock"
        sock_path.touch()

        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch("ananta.ananta.ContainerPool", return_value=MagicMock(spec=ContainerPool)),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run") as mock_run,
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [sock_path]),
            patch.object(Path, "is_socket", return_value=True),
        ):
            # returncode=0 but invalid scheme — rejected before from_env
            mock_run.return_value = MagicMock(returncode=0, stdout="not a valid url\n")
            mock_docker.from_env.return_value = mock_client
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            ananta.start()

            # from_env called only once (Strategy 3 path probing), not for garbage
            assert mock_docker.from_env.call_count == 1
            mock_client.close.assert_called_once()

    def test_check_docker_skips_path_that_exists_but_not_socket(self, tmp_path: Path):
        """Paths that exist but aren't sockets are skipped with diagnostic."""
        regular_file = tmp_path / "docker.sock"
        regular_file.touch()  # regular file, not a socket

        with (
            patch("ananta.ananta.docker"),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [regular_file]),
            patch.object(Path, "is_socket", return_value=False),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            with pytest.raises(RuntimeError, match="exists but not a socket"):
                ananta.start()

    def test_check_docker_skips_nonexistent_path(self, tmp_path: Path):
        """Paths that don't exist are skipped with 'not found' diagnostic."""
        missing = tmp_path / "nonexistent.sock"

        with (
            patch("ananta.ananta.docker"),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [missing]),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            with pytest.raises(RuntimeError, match="not found"):
                ananta.start()

    def test_check_docker_error_includes_podman_guidance(self, tmp_path: Path):
        """When all discovery fails, error message includes Podman guidance."""
        with (
            patch("ananta.ananta.docker"),
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", []),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            with pytest.raises(RuntimeError) as exc_info:
                ananta.start()

            error_msg = str(exc_info.value)
            assert "Could not connect to Docker" in error_msg
            assert "DOCKER_HOST" in error_msg
            assert "Podman" in error_msg or "podman" in error_msg
            assert "Tried:" in error_msg

    def test_docker_host_cleaned_up_on_non_docker_exception_strategy2(self, tmp_path: Path):
        """DOCKER_HOST is cleaned up even if from_env() raises a non-DockerException."""
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run") as mock_run,
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", []),
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="unix:///test/docker.sock\n",
            )
            mock_docker.from_env.side_effect = ValueError("unexpected SDK error")
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError, match="Could not connect"):
                ananta.start()

            assert "DOCKER_HOST" not in os.environ

    def test_docker_host_cleaned_up_on_non_docker_exception_strategy3(self, tmp_path: Path):
        """DOCKER_HOST is cleaned up from Strategy 3 on non-DockerException."""
        sock_path = tmp_path / "docker.sock"
        sock_path.touch()

        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [sock_path]),
            patch.object(Path, "is_socket", return_value=True),
        ):
            mock_docker.from_env.side_effect = ValueError("unexpected SDK error")
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError, match="Could not connect"):
                ananta.start()

            assert "DOCKER_HOST" not in os.environ

    def test_original_docker_host_restored_on_total_failure(self, tmp_path: Path):
        """User's original DOCKER_HOST is restored when all strategies fail."""
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch.dict(os.environ, {"DOCKER_HOST": "unix:///user/custom.sock"}),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", []),
        ):
            mock_docker.from_env.side_effect = DockerException("Connection refused")
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError, match="Could not connect"):
                ananta.start()

            assert os.environ.get("DOCKER_HOST") == "unix:///user/custom.sock"

    def test_check_docker_rejects_invalid_context_output(self, tmp_path: Path):
        """docker context inspect output without a known scheme is rejected."""
        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run") as mock_run,
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", []),
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="WARNING: some garbage output\n",
            )
            mock_docker.from_env.side_effect = DockerException("fail")
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(RuntimeError, match="Could not connect"):
                ananta.start()

            # from_env should NOT have been called — the output was rejected
            mock_docker.from_env.assert_not_called()

    def test_check_docker_accepts_valid_schemes(self, tmp_path: Path):
        """docker context inspect output with unix://, tcp://, npipe:// is accepted."""
        for scheme in ["unix:///var/run/docker.sock", "tcp://127.0.0.1:2375", "npipe:////./pipe/docker"]:
            mock_client = MagicMock()
            with (
                patch("ananta.ananta.docker") as mock_docker,
                patch("ananta.ananta.ContainerPool", return_value=MagicMock(spec=ContainerPool)),
                patch.dict(os.environ, {}, clear=True),
                patch("ananta.ananta.subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=f"{scheme}\n",
                )
                mock_docker.from_env.return_value = mock_client
                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.start()

                mock_docker.from_env.assert_called_once()

    def test_docker_discovery_uses_class_level_lock(self, tmp_path: Path):
        """_check_docker_available uses a class-level lock to protect os.environ."""
        assert hasattr(Ananta, "_docker_discovery_lock")
        assert isinstance(Ananta._docker_discovery_lock, type(threading.Lock()))

    def test_check_docker_error_when_socket_found_but_not_responding(self, tmp_path: Path):
        """When socket exists but Docker doesn't respond, distinct error."""
        sock_path = tmp_path / "docker.sock"
        sock_path.touch()

        with (
            patch("ananta.ananta.docker") as mock_docker,
            patch.dict(os.environ, {}, clear=True),
            patch("ananta.ananta.subprocess.run", side_effect=FileNotFoundError),
            patch("ananta.ananta.Ananta._KNOWN_SOCKET_PATHS", [sock_path]),
            patch.object(Path, "is_socket", return_value=True),
        ):
            mock_docker.from_env.side_effect = DockerException("Connection refused")
            ananta = Ananta(model="test-model", storage_path=tmp_path)
            with pytest.raises(RuntimeError) as exc_info:
                ananta.start()

            error_msg = str(exc_info.value)
            assert "not responding" in error_msg


class TestAnanta:
    """Tests for Ananta class."""

    def test_create_project(self, tmp_path: Path):
        """Creating a project returns a Project instance."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        project = ananta.create_project("my-project")

        assert project.project_id == "my-project"

    def test_list_projects(self, tmp_path: Path):
        """List projects returns project IDs."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        ananta.create_project("project-a")
        ananta.create_project("project-b")

        projects = ananta.list_projects()
        assert "project-a" in projects
        assert "project-b" in projects

    def test_get_project(self, tmp_path: Path):
        """Get project returns existing project."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        ananta.create_project("existing")

        project = ananta.get_project("existing")
        assert project.project_id == "existing"

    def test_delete_project(self, tmp_path: Path):
        """Delete project removes it."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        ananta.create_project("to-delete")
        ananta.delete_project("to-delete")

        assert "to-delete" not in ananta.list_projects()

    def test_register_parser(self, tmp_path: Path):
        """Register custom parser adds it to the registry."""
        ananta = Ananta(model="test-model", storage_path=tmp_path)

        # Create a mock custom parser
        mock_parser = MagicMock()
        mock_parser.can_parse.return_value = True

        ananta.register_parser(mock_parser)

        # The parser should now be findable through the public API.
        # Use a file extension no built-in parser handles so it matches
        # our mock (whose can_parse returns True for everything).
        assert ananta.parser_registry.find_parser(Path("test.xyz123")) is mock_parser

    def test_stop_after_restart_stops_pool(self, tmp_path: Path):
        """Stop after start-stop-start cycle should stop the pool."""

        mock_pool = MagicMock(spec=ContainerPool)
        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            # First cycle: start then stop
            ananta.start()
            ananta.stop()

            # Second cycle: start again
            ananta.start()

            # Reset call count to track second stop
            mock_pool.stop.reset_mock()

            # Second stop should call pool.stop()
            ananta.stop()

            mock_pool.stop.assert_called_once()

    def test_ananta_passes_pool_to_engine_on_start(self, tmp_path: Path):
        """Ananta passes pool to RLMEngine via set_pool() when start() is called."""
        mock_pool = MagicMock()
        with (
            patch("ananta.ananta.docker"),
            patch("ananta.ananta.ContainerPool", return_value=mock_pool),
        ):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with patch.object(ananta.rlm_engine, "set_pool") as mock_set:
                ananta.start()
                mock_set.assert_called_once_with(mock_pool)

    def test_ananta_uses_config_load_by_default(self, tmp_path: Path):
        """Ananta uses AnantaConfig.load() by default, picking up env vars."""

        with patch.dict(os.environ, {"ANANTA_MAX_ITERATIONS": "99"}):
            ananta = Ananta(storage_path=tmp_path)
            assert ananta.rlm_engine.max_iterations == 99

    def test_delete_project_cleans_up_remote_repo(self, tmp_path: Path):
        """delete_project removes cloned repo for remote projects by default."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("to-delete")

                ananta.delete_project("to-delete")

                mock_ingester.delete_repo.assert_called_once_with("to-delete")

    def test_delete_project_skips_cleanup_for_local_repo(self, tmp_path: Path):
        """delete_project does not call delete_repo for local repos."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/path/to/local/repo"
                mock_ingester.is_local_path.return_value = True

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("local-project")

                ananta.delete_project("local-project")

                mock_ingester.delete_repo.assert_not_called()

    def test_delete_project_respects_cleanup_repo_false(self, tmp_path: Path):
        """delete_project skips repo cleanup when cleanup_repo=False."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("to-delete")

                ananta.delete_project("to-delete", cleanup_repo=False)

                mock_ingester.delete_repo.assert_not_called()


class TestCreateProjectFromRepo:
    """Tests for create_project_from_repo method."""

    def test_creates_new_project(self, tmp_path: Path):
        """create_project_from_repo creates project for new repo."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                # ingest() creates the project and returns result
                def fake_ingest(**kwargs):
                    ananta.storage.create_project("my-project")
                    return IngestResult(files_ingested=1)

                mock_ingester.ingest.side_effect = fake_ingest

                result = ananta.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="my-project",
                )

                assert isinstance(result, RepoProjectResult)
                assert result.status == "created"
                assert result.project.project_id == "my-project"

    def test_unchanged_when_sha_matches(self, tmp_path: Path):
        """create_project_from_repo returns unchanged when SHAs match."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "abc123"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_unchanged_when_both_shas_none(self, tmp_path: Path):
        """When both saved and remote SHAs are None, treat as unchanged."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_remote_sha.return_value = None
                mock_ingester.get_saved_path.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_check_failed_when_remote_sha_is_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """When saved_sha exists but remote SHA is None (network failure),
        return check_failed instead of updates_available."""

        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                with caplog.at_level(logging.WARNING, logger="ananta.ananta"):
                    result = ananta.create_project_from_repo(
                        url="https://github.com/org/repo",
                        name="my-project",
                    )

                assert result.status == "check_failed"
                assert any("Could not determine current SHA" in r.message for r in caplog.records)

    def test_unchanged_when_saved_sha_none_but_current_sha_valid(self, tmp_path: Path):
        """When saved_sha is None (e.g. SHA save failed during initial ingest)
        but current_sha is valid, treat as unchanged — not false updates_available."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_remote_sha.return_value = "abc123"
                mock_ingester.get_saved_path.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "unchanged"

    def test_updates_available_when_sha_differs(self, tmp_path: Path):
        """create_project_from_repo returns updates_available when SHAs differ."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="my-project",
                )

                assert result.status == "updates_available"

    def test_preserves_saved_path_when_caller_passes_none(self, tmp_path: Path):
        """When create_project_from_repo is called with path=None for a project
        that was originally created with a subdirectory scope, the apply_updates
        closure should use the saved path, not None."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"
                mock_ingester.get_saved_path.return_value = "src/"
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("scoped-project")

                # Caller passes path=None (the default)
                result = ananta.create_project_from_repo(
                    url="https://github.com/org/repo",
                    name="scoped-project",
                )

                assert result.status == "updates_available"

                mock_ingester.ingest.return_value = IngestResult(files_ingested=2)
                result.apply_updates()

                # Verify ingest was called with the saved path, not None
                call_kwargs = mock_ingester.ingest.call_args[1]
                assert call_kwargs["path"] == "src/"

    def test_apply_updates_skips_pull_for_local_repos(self, tmp_path: Path):
        """apply_updates() should not call pull() for local repositories."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Simulate a local repo with updates available
                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_sha_from_path.return_value = "def456"  # Different SHA
                mock_ingester.list_files_from_path.return_value = []
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("local-project")

                result = ananta.create_project_from_repo(
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
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                def fake_ingest(**kwargs):
                    ananta.storage.create_project("my-project")
                    return IngestResult(files_ingested=0)

                mock_ingester.ingest.side_effect = fake_ingest

                ananta.create_project_from_repo(
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
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                def fake_ingest(**kwargs):
                    ananta.storage.create_project("my-project")
                    return IngestResult(files_ingested=0)

                mock_ingester.ingest.side_effect = fake_ingest

                ananta.create_project_from_repo(
                    url="./myrepo",
                    name="my-project",
                )

                # URL is passed through to ingest()
                call_kwargs = mock_ingester.ingest.call_args[1]
                assert call_kwargs["url"] == "./myrepo"

    def test_raises_for_non_git_local_path(self, tmp_path: Path):
        """create_project_from_repo raises RepoIngestError for non-git local dirs."""

        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = False

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError) as exc_info:
                    ananta.create_project_from_repo(
                        url="/path/to/non-git-dir",
                        name="my-project",
                    )

                assert "not a git repository" in str(exc_info.value).lower()


class TestAtomicIngestion:
    """Tests for atomic repo ingestion (stage-then-swap for updates, cleanup on failure)."""

    def test_failed_new_project_ingestion_propagates_error(self, tmp_path: Path):
        """Failed ingestion propagates error from ingest()."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"
                mock_ingester.ingest.side_effect = RepoIngestError(
                    "/path/to/local/repo", cause=OSError("disk full")
                )

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError):
                    ananta.create_project_from_repo(
                        url="/path/to/local/repo",
                        name="clean-on-fail",
                    )

    def test_failed_update_propagates_error(self, tmp_path: Path):
        """Failed update propagates error from ingest()."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("update-project")

                result = ananta.create_project_from_repo(
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
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("orphan-project")

                result = ananta.create_project_from_repo(
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
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.list_files_from_path.return_value = ["file.py"]
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                # Create a user project whose name matches the old staging pattern
                ananta.storage.create_project("_staging_my-project")

                original_doc = ParsedDocument(
                    name="original.txt",
                    content="original",
                    format="txt",
                    metadata={},
                    char_count=8,
                    parse_warnings=[],
                )
                ananta.storage.store_document("my-project", original_doc)

                result = ananta.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="my-project",
                )

                assert result.status == "updates_available"

                with patch.object(ananta.parser_registry, "find_parser") as mock_find:
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
                assert ananta.storage.project_exists("_staging_my-project")

    def test_update_passes_custom_storage_to_ingest(self, tmp_path: Path):
        """Updates pass the custom storage backend to ingest()."""

        real_storage = FilesystemStorage(root_path=tmp_path)

        class CustomStorage:
            """Wrapper that delegates to FilesystemStorage but isn't one."""

            def __init__(self, inner: FilesystemStorage):
                self._inner = inner

            def __getattr__(self, name: str) -> object:
                return getattr(self._inner, name)

        custom: StorageBackend = CustomStorage(real_storage)  # type: ignore[assignment]

        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path, storage=custom)
                real_storage.create_project("custom-project")

                result = ananta.create_project_from_repo(
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
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "old_sha"
                mock_ingester.get_sha_from_path.return_value = "new_sha"
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("flag-project")

                result = ananta.create_project_from_repo(
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
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                def fake_ingest(**kwargs):
                    ananta.storage.create_project("parse-err-project")
                    return IngestResult(
                        files_ingested=0,
                        files_skipped=1,
                        warnings=["Failed to parse bad.py: syntax error"],
                    )

                mock_ingester.ingest.side_effect = fake_ingest

                result = ananta.create_project_from_repo(
                    url="/path/to/local/repo",
                    name="parse-err-project",
                )

                assert result.files_skipped == 1
                assert any("bad.py" in w for w in result.warnings)

    def test_unexpected_error_propagates_from_ingest(self, tmp_path: Path):
        """RepoIngestError from ingest() propagates through _ingest_repo."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = True
                mock_ingester.is_git_repo.return_value = True
                mock_ingester.repos_dir = tmp_path / "repos"
                mock_ingester.ingest.side_effect = RepoIngestError(
                    "/path/to/local/repo", cause=OSError("disk full")
                )

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError) as exc_info:
                    ananta.create_project_from_repo(
                        url="/path/to/local/repo",
                        name="crash-project",
                    )

                assert isinstance(exc_info.value.__cause__, OSError)

    def test_failed_new_remote_project_error_from_ingest(self, tmp_path: Path):
        """Failed ingestion of a new remote project propagates from ingest()."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.is_local_path.return_value = False
                mock_ingester.repos_dir = tmp_path / "repos"
                mock_ingester.ingest.side_effect = RepoIngestError(
                    "https://github.com/org/repo", cause=OSError("disk full")
                )

                ananta = Ananta(model="test-model", storage_path=tmp_path)

                with pytest.raises(RepoIngestError):
                    ananta.create_project_from_repo(
                        url="https://github.com/org/repo",
                        name="remote-project",
                    )


class TestCheckRepoForUpdates:
    """Tests for check_repo_for_updates method."""

    def test_returns_unchanged_when_no_updates(self, tmp_path: Path):
        """check_repo_for_updates returns unchanged when repo is current."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Cloned repo with matching SHAs
                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "abc123"
                mock_ingester.resolve_token.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.check_repo_for_updates("my-project")

                assert result.status == "unchanged"
                assert result.project.project_id == "my-project"

    def test_returns_updates_available_when_sha_differs(self, tmp_path: Path):
        """check_repo_for_updates returns updates_available when SHAs differ."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Cloned repo with different SHAs
                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"
                mock_ingester.resolve_token.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.check_repo_for_updates("my-project")

                assert result.status == "updates_available"

    def test_returns_unchanged_when_both_shas_none(self, tmp_path: Path):
        """Both SHAs None should return unchanged, not false updates_available."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = None
                mock_ingester.get_remote_sha.return_value = None
                mock_ingester.resolve_token.return_value = None
                mock_ingester.get_saved_path.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.check_repo_for_updates("my-project")

                assert result.status == "unchanged"

    def test_raises_when_project_not_found(self, tmp_path: Path):
        """check_repo_for_updates raises ProjectNotFoundError for non-existent project."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(ProjectNotFoundError) as exc_info:
                ananta.check_repo_for_updates("nonexistent")

            assert "does not exist" in str(exc_info.value)

    def test_raises_when_no_repo_url(self, tmp_path: Path):
        """check_repo_for_updates raises RepoError when no repo URL stored."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # No repo URL stored (not a cloned repo)
                mock_ingester.get_source_url.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                with pytest.raises(RepoError) as exc_info:
                    ananta.check_repo_for_updates("my-project")

                assert "No repository URL" in str(exc_info.value)

    def test_works_with_local_repo(self, tmp_path: Path):
        """check_repo_for_updates works with local repos using get_source_url."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                # Local repo - get_repo_url returns None (no cloned dir)
                # but get_source_url returns the local path
                mock_ingester.get_source_url.return_value = "/path/to/local/repo"
                mock_ingester.is_local_path.return_value = True
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_sha_from_path.return_value = "abc123"
                mock_ingester.resolve_token.return_value = None

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.check_repo_for_updates("my-project")

                assert result.status == "unchanged"
                assert result.project.project_id == "my-project"
                # Verify it used get_source_url, not get_repo_url
                mock_ingester.get_source_url.assert_called_once_with("my-project")

    def test_loads_saved_path_for_subdirectory_scoped_project(self, tmp_path: Path):
        """check_repo_for_updates loads saved path and passes it through."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False
                mock_ingester.get_saved_sha.return_value = "abc123"
                mock_ingester.get_remote_sha.return_value = "def456"
                mock_ingester.resolve_token.return_value = None
                mock_ingester.get_saved_path.return_value = "src/"

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                result = ananta.check_repo_for_updates("my-project")

                assert result.status == "updates_available"
                # The apply_updates closure must use the saved path
                # We verify by checking _handle_existing_project received it
                mock_ingester.get_saved_path.assert_called_once_with("my-project")


class TestGetProjectInfo:
    """Tests for get_project_info method."""

    def test_returns_info_for_remote_repo(self, tmp_path: Path):
        """get_project_info returns correct info for remote repo project."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "https://github.com/org/repo"
                mock_ingester.is_local_path.return_value = False

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("my-project")

                info = ananta.get_project_info("my-project")

                assert info.project_id == "my-project"
                assert info.source_url == "https://github.com/org/repo"
                assert info.is_local is False
                assert info.source_exists is True

    def test_returns_info_for_existing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=True when local path exists."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                local_path = tmp_path / "local_repo"
                local_path.mkdir()

                mock_ingester.get_source_url.return_value = str(local_path)
                mock_ingester.is_local_path.return_value = True

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("local-project")

                info = ananta.get_project_info("local-project")

                assert info.is_local is True
                assert info.source_exists is True

    def test_returns_info_for_missing_local_repo(self, tmp_path: Path):
        """get_project_info returns source_exists=False when local path missing."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester

                mock_ingester.get_source_url.return_value = "/nonexistent/path"
                mock_ingester.is_local_path.return_value = True

                ananta = Ananta(model="test-model", storage_path=tmp_path)
                ananta.storage.create_project("missing-project")

                info = ananta.get_project_info("missing-project")

                assert info.is_local is True
                assert info.source_exists is False

    def test_raises_for_nonexistent_project(self, tmp_path: Path):
        """get_project_info raises ProjectNotFoundError for non-existent project."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            ananta = Ananta(model="test-model", storage_path=tmp_path)

            with pytest.raises(ProjectNotFoundError) as exc_info:
                ananta.get_project_info("nonexistent")

            assert "does not exist" in str(exc_info.value)


class TestExtractRepoName:
    """Tests for _extract_repo_name method."""

    def _make_ananta(self, tmp_path: Path, is_local: bool = False) -> Ananta:
        """Create an Ananta instance with mocked Docker and RepoIngester."""
        with patch("ananta.ananta.docker"), patch("ananta.ananta.ContainerPool"):
            with patch("ananta.ananta.RepoIngester") as mock_ingester_cls:
                mock_ingester = MagicMock()
                mock_ingester_cls.return_value = mock_ingester
                mock_ingester.is_local_path.return_value = is_local
                ananta = Ananta(model="test-model", storage_path=tmp_path)
        return ananta

    def test_https_url(self, tmp_path: Path):
        """Standard HTTPS GitHub URL extracts org-repo name."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("https://github.com/Ovid/ananta") == "Ovid-ananta"

    def test_https_url_trailing_slash(self, tmp_path: Path):
        """HTTPS URL with trailing slash extracts org-repo name."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("https://github.com/Ovid/ananta/") == "Ovid-ananta"

    def test_https_url_dot_git(self, tmp_path: Path):
        """HTTPS URL with .git suffix extracts org-repo name."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("https://github.com/Ovid/ananta.git") == "Ovid-ananta"

    def test_https_url_dot_git_trailing_slash(self, tmp_path: Path):
        """HTTPS URL with .git and trailing slash extracts org-repo name."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("https://github.com/Ovid/ananta.git/") == "Ovid-ananta"

    def test_ssh_url(self, tmp_path: Path):
        """SSH git URL extracts org-repo name."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("git@github.com:Ovid/ananta.git") == "Ovid-ananta"

    def test_gitlab_url(self, tmp_path: Path):
        """GitLab URL extracts org-repo name."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("https://gitlab.com/myorg/myrepo") == "myorg-myrepo"

    def test_local_path_uses_parent_and_name(self, tmp_path: Path):
        """Local path extracts parent-name to avoid collisions."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        assert ananta._extract_repo_name("/home/user/projects/ananta") == "projects-ananta"

    def test_local_home_relative_path(self, tmp_path: Path):
        """Home-relative local path extracts parent-name."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        assert ananta._extract_repo_name("~/projects/myrepo") == "projects-myrepo"

    def test_local_path_trailing_slash(self, tmp_path: Path):
        """Local path with trailing slash extracts parent-name."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        assert ananta._extract_repo_name("/home/user/projects/ananta/") == "projects-ananta"

    def test_local_relative_path_no_leading_dash(self, tmp_path: Path):
        """Relative local path without parent resolves to avoid leading dash."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        result = ananta._extract_repo_name("myrepo")
        assert not result.startswith("-"), f"Name should not start with dash: {result}"
        assert result.endswith("myrepo")

    def test_local_dot_relative_path(self, tmp_path: Path):
        """Dot-relative local path resolves to meaningful parent-name."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        result = ananta._extract_repo_name("./myrepo")
        assert not result.startswith("-"), f"Name should not start with dash: {result}"
        assert not result.startswith("."), f"Name should not start with dot: {result}"
        assert result.endswith("myrepo")

    def test_local_path_with_spaces_sanitized(self, tmp_path: Path):
        """Local path with spaces produces a safe slug without spaces."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        result = ananta._extract_repo_name("/home/user/my projects/my repo")
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
        result = Ananta._sanitize_project_id(raw)
        assert re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", result), (
            f"_sanitize_project_id({raw!r}) = {result!r} does not match _SAFE_ID_RE"
        )

    def test_local_hidden_dir_produces_safe_id(self, tmp_path: Path):
        """Local path under a hidden directory produces a _SAFE_ID_RE-valid ID."""
        ananta = self._make_ananta(tmp_path, is_local=True)
        result = ananta._extract_repo_name("/home/user/.config/.repo")
        assert re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", result), (
            f"Result {result!r} does not match _SAFE_ID_RE"
        )

    def test_fallback_for_unparseable_url(self, tmp_path: Path):
        """Unparseable URL falls back to unnamed-repo."""
        ananta = self._make_ananta(tmp_path)
        assert ananta._extract_repo_name("not-a-url") == "unnamed-repo"


class TestGetProjectInfoWithAnalysis:
    """Tests for get_project_info including analysis_status."""

    def test_get_project_info_includes_analysis_status(self, ananta_instance):
        """get_project_info includes analysis_status field."""
        ananta_instance.create_project("info-with-status")

        info = ananta_instance.get_project_info("info-with-status")

        assert info.analysis_status == "missing"  # No analysis yet

    def test_get_project_info_analysis_status_current(self, ananta_instance):
        """get_project_info shows 'current' when analysis matches SHA."""

        ananta_instance.create_project("info-current")
        ananta_instance.repo_ingester.save_sha("info-current", "sha123")
        ananta_instance.repo_ingester.save_source_url("info-current", "/fake")

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="sha123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        ananta_instance.storage.store_analysis("info-current", analysis)

        info = ananta_instance.get_project_info("info-current")

        assert info.analysis_status == "current"

    def test_get_project_info_analysis_status_stale(self, ananta_instance):
        """get_project_info shows 'stale' when analysis SHA differs from current."""

        ananta_instance.create_project("info-stale")
        ananta_instance.repo_ingester.save_sha("info-stale", "new_sha")
        ananta_instance.repo_ingester.save_source_url("info-stale", "/fake")

        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="old_sha",  # Different from saved SHA
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        ananta_instance.storage.store_analysis("info-stale", analysis)

        info = ananta_instance.get_project_info("info-stale")

        assert info.analysis_status == "stale"


class TestAnalysisStatus:
    """Tests for analysis status checking."""

    def test_get_analysis_status_missing(self, ananta_instance: Ananta, tmp_path: Path):
        """get_analysis_status returns 'missing' when no analysis exists."""
        ananta_instance.create_project("no-analysis-project")
        status = ananta_instance.get_analysis_status("no-analysis-project")
        assert status == "missing"

    def test_get_analysis_status_current(self, ananta_instance: Ananta, tmp_path: Path):
        """get_analysis_status returns 'current' when analysis matches HEAD."""

        ananta_instance.create_project("current-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        ananta_instance.storage.store_analysis("current-analysis", analysis)
        ananta_instance.repo_ingester.save_sha("current-analysis", "abc123")
        ananta_instance.repo_ingester.save_source_url("current-analysis", "/fake/path")

        status = ananta_instance.get_analysis_status("current-analysis")
        assert status == "current"

    def test_get_analysis_status_stale(self, ananta_instance: Ananta, tmp_path: Path):
        """get_analysis_status returns 'stale' when analysis SHA differs from HEAD."""

        ananta_instance.create_project("stale-analysis")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="old_sha_123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        ananta_instance.storage.store_analysis("stale-analysis", analysis)
        ananta_instance.repo_ingester.save_sha("stale-analysis", "new_sha_456")
        ananta_instance.repo_ingester.save_source_url("stale-analysis", "/fake/path")

        status = ananta_instance.get_analysis_status("stale-analysis")
        assert status == "stale"

    def test_get_analysis_status_stale_when_sha_unknown(
        self, ananta_instance: Ananta, tmp_path: Path
    ):
        """get_analysis_status returns 'stale' when saved SHA is None but analysis exists."""

        ananta_instance.create_project("unknown-sha")
        analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test",
            components=[],
            external_dependencies=[],
        )
        ananta_instance.storage.store_analysis("unknown-sha", analysis)
        # No SHA saved — get_saved_sha will return None

        status = ananta_instance.get_analysis_status("unknown-sha")
        assert status == "stale"

    def test_get_analysis_status_nonexistent_project_raises(self, ananta_instance: Ananta):
        """get_analysis_status raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError, match="does not exist"):
            ananta_instance.get_analysis_status("no-such-project")


class TestGetAnalysis:
    """Tests for get_analysis method."""

    def test_get_analysis_returns_stored_analysis(self, ananta_instance: Ananta):
        """get_analysis returns the stored analysis."""

        ananta_instance.create_project("get-analysis-project")
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
        ananta_instance.storage.store_analysis("get-analysis-project", analysis)

        result = ananta_instance.get_analysis("get-analysis-project")
        assert result is not None
        assert result.overview == "Test app"
        assert len(result.components) == 1

    def test_get_analysis_returns_none_when_missing(self, ananta_instance: Ananta):
        """get_analysis returns None when no analysis exists."""
        ananta_instance.create_project("no-analysis")
        result = ananta_instance.get_analysis("no-analysis")
        assert result is None

    def test_get_analysis_nonexistent_project_raises(self, ananta_instance: Ananta):
        """get_analysis raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError, match="does not exist"):
            ananta_instance.get_analysis("no-such-project")


class TestGenerateAnalysis:
    """Tests for generate_analysis method."""

    def test_generate_analysis_stores_result(self, ananta_instance):
        """generate_analysis stores the generated analysis."""

        # Create a project
        ananta_instance.create_project("gen-analysis")
        ananta_instance.repo_ingester.save_sha("gen-analysis", "sha123")

        # Mock the generator
        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="sha123",
            overview="Generated analysis",
            components=[],
            external_dependencies=[],
        )

        with patch("ananta.ananta.AnalysisGenerator") as mock_generator:
            mock_generator.return_value.generate.return_value = mock_analysis

            result = ananta_instance.generate_analysis("gen-analysis")

            assert result.overview == "Generated analysis"
            # Verify it was stored
            stored = ananta_instance.storage.load_analysis("gen-analysis")
            assert stored is not None
            assert stored.overview == "Generated analysis"

    def test_generate_analysis_returns_analysis(self, ananta_instance):
        """generate_analysis returns the generated RepoAnalysis."""

        ananta_instance.create_project("return-analysis")

        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc",
            overview="Test",
            components=[],
            external_dependencies=[],
        )

        with patch("ananta.ananta.AnalysisGenerator") as mock_generator:
            mock_generator.return_value.generate.return_value = mock_analysis

            result = ananta_instance.generate_analysis("return-analysis")

            assert isinstance(result, RepoAnalysis)
            assert result.overview == "Test"

    def test_generate_analysis_nonexistent_project_raises(self, ananta_instance):
        """generate_analysis raises for nonexistent project."""
        with pytest.raises(ProjectNotFoundError, match="does not exist"):
            ananta_instance.generate_analysis("no-such-project")
