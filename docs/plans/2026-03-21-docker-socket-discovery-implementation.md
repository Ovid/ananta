# Docker Socket Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-detect Docker sockets, show clean error messages instead of stacktraces, and make Docker connection failures easy to debug.

**Architecture:** Rewrite `_check_docker_available()` with a multi-strategy socket discovery (env var → docker context CLI → known paths). Catch startup errors in the FastAPI lifespan to suppress stacktraces. Set `os.environ["DOCKER_HOST"]` when a non-default socket is discovered so both `ananta.py` and `executor.py` call sites benefit (design refinement — threading `base_url` through 4 layers was rejected as unnecessary plumbing since Ananta owns the process).

**Tech Stack:** Python `docker` library, `subprocess` for Docker CLI, `pathlib` for socket probing.

**Design doc:** `docs/plans/2026-03-21-docker-socket-discovery-design.md`

---

### Task 1: Refactor discovery logic — test DOCKER_HOST already set

**Files:**
- Modify: `tests/unit/test_ananta.py` (class `TestDockerAvailability`)
- Modify: `src/ananta/ananta.py:139-158`

**Step 1: Write the failing test**

Add to `tests/unit/test_ananta.py` inside `TestDockerAvailability`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_respects_existing_docker_host -v`
Expected: PASS (current code already calls `from_env()` which reads `DOCKER_HOST`). This is a baseline test — it documents the existing behavior before we change the method.

**Step 3: Commit**

```
git add tests/unit/test_ananta.py
git commit -m "test: add baseline test for DOCKER_HOST being respected"
```

---

### Task 2: Test docker context inspect discovery

**Files:**
- Modify: `tests/unit/test_ananta.py`

**Step 1: Write the failing test**

```python
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

        # Should have set DOCKER_HOST from context inspect result
        mock_docker.from_env.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_uses_context_inspect_when_no_docker_host -v`
Expected: FAIL — current code does not import or call `subprocess`.

**Step 3: Write minimal implementation — start building the new `_check_docker_available()`**

In `src/ananta/ananta.py`, add `import subprocess` to the imports at top of file. Then replace `_check_docker_available()`:

```python
@staticmethod
def _check_docker_available() -> None:
    """Discover Docker socket and verify daemon is running.

    Strategy:
    1. If DOCKER_HOST is set, use it directly.
    2. Try ``docker context inspect`` to get the active socket.
    3. Probe known socket paths on disk.
    4. Give up with a diagnostic error message.

    Raises RuntimeError with a clean message if Docker is unreachable.
    """
    import subprocess

    diagnostics: list[str] = []

    # Strategy 1: DOCKER_HOST already set — use it directly.
    if os.environ.get("DOCKER_HOST"):
        diagnostics.append(f"DOCKER_HOST={os.environ['DOCKER_HOST']}")
        try:
            client = docker.from_env()
            client.close()
            return
        except DockerException as e:
            diagnostics[-1] += " — not responding"
            logger.debug("DOCKER_HOST set but failed: %s", e)
    else:
        diagnostics.append("DOCKER_HOST not set")

    # Strategy 2: docker context inspect
    try:
        result = subprocess.run(
            [
                "docker", "context", "inspect",
                "--format", "{{.Endpoints.docker.Host}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            socket_url = result.stdout.strip()
            diagnostics.append(f"docker context: {socket_url}")
            os.environ["DOCKER_HOST"] = socket_url
            try:
                client = docker.from_env()
                client.close()
                return
            except DockerException as e:
                diagnostics[-1] += " — not responding"
                logger.debug("docker context socket failed: %s", e)
                del os.environ["DOCKER_HOST"]
        else:
            stderr = result.stderr.strip()
            diagnostics.append(
                f"docker context: failed ({stderr})" if stderr
                else "docker context: no socket returned"
            )
    except FileNotFoundError:
        diagnostics.append("docker context: docker CLI not found")
    except subprocess.TimeoutExpired:
        diagnostics.append("docker context: timed out")
    except Exception as e:
        diagnostics.append(f"docker context: {e}")
        logger.debug("docker context inspect failed: %s", e)

    # Strategy 3: probe known socket paths
    known_paths = [
        Path("/var/run/docker.sock"),
        Path.home() / ".docker" / "run" / "docker.sock",
        Path.home() / ".colima" / "default" / "docker.sock",
    ]
    for sock_path in known_paths:
        if not sock_path.exists():
            diagnostics.append(f"{sock_path} — not found")
            continue
        if not sock_path.is_socket():
            diagnostics.append(f"{sock_path} — exists but not a socket")
            continue
        socket_url = f"unix://{sock_path}"
        diagnostics.append(f"{sock_path} — found")
        os.environ["DOCKER_HOST"] = socket_url
        try:
            client = docker.from_env()
            client.close()
            return
        except DockerException as e:
            diagnostics[-1] += " — not responding"
            logger.debug("Socket %s found but failed: %s", sock_path, e)
            del os.environ["DOCKER_HOST"]

    # Strategy 4: give up
    tried = "\n    ".join(f"x {d}" for d in diagnostics)
    raise RuntimeError(
        "Could not connect to Docker.\n\n"
        f"  Tried:\n    {tried}\n\n"
        "  To fix, either:\n"
        "    - Start Docker Desktop\n"
        "    - Set DOCKER_HOST to your Docker socket path\n"
        "    - If using Podman: export DOCKER_HOST=\"unix://$("
        "podman machine inspect "
        "--format '{{.ConnectionInfo.PodmanSocket.Path}}')\""
    )
```

Also add `import os` and `import subprocess` to the top of `ananta.py` if not already present. (`os` is already imported in tests but check `ananta.py`.)

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_uses_context_inspect_when_no_docker_host -v`
Expected: PASS

**Step 5: Commit**

```
git add src/ananta/ananta.py tests/unit/test_ananta.py
git commit -m "feat: add Docker socket discovery via docker context inspect"
```

---

### Task 3: Test silent fallthrough when docker context fails

**Files:**
- Modify: `tests/unit/test_ananta.py`

**Step 1: Write the failing tests**

```python
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
    """When docker context inspect returns success but unparseable output, falls through."""
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
        # returncode=0 but garbage output — from_env will fail with this as DOCKER_HOST
        mock_run.return_value = MagicMock(returncode=0, stdout="not a valid url\n")
        mock_docker.from_env.side_effect = [
            DockerException("Invalid URL"),  # first call with garbage URL fails
            mock_client,  # second call after path probing succeeds
        ]
        ananta = Ananta(model="test-model", storage_path=tmp_path)
        ananta.start()

        assert mock_docker.from_env.call_count == 2
        mock_client.close.assert_called_once()
```

Note: these tests reference `_KNOWN_SOCKET_PATHS` — a class attribute that makes the known paths list patchable in tests. Extract the hardcoded list in `_check_docker_available()` to:

```python
_KNOWN_SOCKET_PATHS: ClassVar[list[Path]] = [
    Path("/var/run/docker.sock"),
    Path.home() / ".docker" / "run" / "docker.sock",
    Path.home() / ".colima" / "default" / "docker.sock",
]
```

And reference `cls._KNOWN_SOCKET_PATHS` in the method (change from `@staticmethod` to `@classmethod`).

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_falls_through_when_docker_cli_not_installed tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_falls_through_when_context_returns_nonzero -v`
Expected: FAIL — `_KNOWN_SOCKET_PATHS` doesn't exist yet.

**Step 3: Implement — extract known paths to class attribute**

In `src/ananta/ananta.py`, add `from typing import ClassVar` if needed. Add the class attribute to `Ananta`. Change `_check_docker_available` from `@staticmethod` to `@classmethod` and use `cls._KNOWN_SOCKET_PATHS` instead of the hardcoded list.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability -v`
Expected: ALL PASS

**Step 5: Commit**

```
git add src/ananta/ananta.py tests/unit/test_ananta.py
git commit -m "feat: add fallthrough from docker context to path probing"
```

---

### Task 4: Test known path probing with is_socket check

**Files:**
- Modify: `tests/unit/test_ananta.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_skips_path_that_exists_but_not_socket tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_skips_nonexistent_path -v`
Expected: PASS (implementation from Task 2 already handles these).

**Step 3: Commit**

```
git add tests/unit/test_ananta.py
git commit -m "test: add path probing edge case tests (not-a-socket, not-found)"
```

---

### Task 5: Test diagnostic error message content

**Files:**
- Modify: `tests/unit/test_ananta.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_error_includes_podman_guidance tests/unit/test_ananta.py::TestDockerAvailability::test_check_docker_error_when_socket_found_but_not_responding -v`
Expected: PASS (implementation from Task 2 covers these).

**Step 3: Commit**

```
git add tests/unit/test_ananta.py
git commit -m "test: verify diagnostic error message content and Podman guidance"
```

---

### Task 6: Update existing tests

**Files:**
- Modify: `tests/unit/test_ananta.py`

**Step 1: Update `test_start_checks_docker_and_creates_pool`**

This test asserts `mock_docker.from_env.assert_called_once()`. With the new discovery logic, `from_env()` is still called (once the socket is found), but the test needs to account for the subprocess call. Patch `subprocess.run` to simulate `docker context inspect` failing, and either set `DOCKER_HOST` or provide a known path:

```python
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
```

**Step 2: Update `test_start_raises_clear_error_when_docker_not_running`**

Set `DOCKER_HOST` so discovery goes straight to `from_env()`:

```python
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
```

**Step 3: Update `test_start_raises_helpful_error_when_socket_not_found`**

This test simulated `FileNotFoundError` from `docker.from_env()`. With discovery, the "socket not found" path is now the fallback after all strategies fail. Rewrite to test full discovery failure:

```python
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
```

**Step 4: Run all Docker availability tests**

Run: `pytest tests/unit/test_ananta.py::TestDockerAvailability -v`
Expected: ALL PASS

**Step 5: Commit**

```
git add tests/unit/test_ananta.py
git commit -m "test: update existing Docker availability tests for new discovery logic"
```

---

### Task 7: Remove duplicate Docker error handling from ContainerExecutor

**Files:**
- Modify: `src/ananta/sandbox/executor.py:70-82`
- Modify: `tests/` (any executor tests that test Docker error handling)

**Step 1: Check for existing executor Docker error tests**

Run: `grep -rn "Connection refused\|DockerException\|docker_available" tests/unit/test_executor* tests/unit/test_sandbox*` (or use Grep tool).

**Step 2: Simplify `ContainerExecutor.start()`**

Since `Ananta._check_docker_available()` now runs before any `ContainerExecutor` is created, and sets `DOCKER_HOST` if needed, the executor's error handling is redundant. Simplify to:

```python
def start(self) -> None:
    """Start a container for execution."""
    logger.debug("Starting container (image=%s, memory=%s)", self.image, self.memory_limit)
    self._raw_buffer = b""
    self._content_buffer = b""
    self._client = docker.from_env()
    self._container = self._client.containers.run(
        self.image,
        detach=True,
        stdin_open=True,
        tty=False,
        mem_limit=self.memory_limit,
        cpu_count=self.cpu_count,
        **self.security.to_docker_kwargs(),
    )
    self._socket = self._container.attach_socket(params={"stdin": 1, "stdout": 1, "stream": 1})
```

**Step 3: Run executor tests**

Run: `pytest tests/unit/ -k executor -v`
Expected: PASS

**Step 4: Commit**

```
git add src/ananta/sandbox/executor.py
git commit -m "refactor: remove redundant Docker error handling from ContainerExecutor"
```

---

### Task 8: Catch RuntimeError in lifespan handler

**Files:**
- Modify: `src/ananta/experimental/shared/app_factory.py:55-61`

**Step 1: Write the failing test**

Create test in a new file (no existing test file for `app_factory.py`):

```python
# tests/unit/experimental/shared/test_app_factory.py

import sys
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from ananta.experimental.shared.app_factory import create_app


def test_lifespan_prints_clean_error_on_startup_failure(capsys: pytest.CaptureFixture[str]):
    """When start() raises RuntimeError, lifespan prints message and exits cleanly."""
    state = MagicMock()
    state.ananta.start.side_effect = RuntimeError("Could not connect to Docker.\n\n  Tried:\n    x ...")

    app = create_app(state, title="Test App")

    with pytest.raises(SystemExit) as exc_info:
        with TestClient(app):
            pass

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Could not connect to Docker" in captured.err
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/experimental/shared/test_app_factory.py::test_lifespan_prints_clean_error_on_startup_failure -v`
Expected: FAIL — current lifespan doesn't catch RuntimeError.

**Step 3: Implement**

In `src/ananta/experimental/shared/app_factory.py`, modify the lifespan:

```python
import sys

# ... existing imports ...

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            state.ananta.start()
        except RuntimeError as e:
            print(f"\n[ananta] Error: {e}\n", file=sys.stderr)
            raise SystemExit(1) from e
        try:
            yield
        finally:
            state.ananta.stop()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/experimental/shared/test_app_factory.py -v`
Expected: PASS

**Step 5: Commit**

```
git add src/ananta/experimental/shared/app_factory.py tests/unit/experimental/shared/test_app_factory.py
git commit -m "feat: catch startup RuntimeError in lifespan, print clean error"
```

---

### Task 9: Run full test suite and verify

**Step 1: Run all tests**

Run: `make all`
Expected: ALL PASS — no regressions.

**Step 2: Manual smoke test (if Docker is available)**

Run: `./document-explorer/document-explorer.sh`
Expected: either starts normally (Docker found) or shows clean error message (Docker not found).

**Step 3: Commit any fixups**

If any tests or lint issues arise, fix and commit.

---

### Task 10: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry under `[Unreleased]`**

Under `### Fixed`:

```markdown
- Docker socket auto-discovery — finds Docker Desktop, Colima, and Podman sockets automatically instead of failing with a stacktrace when `/var/run/docker.sock` is missing ([#8](https://github.com/Ovid/ananta/issues/8))
```

**Step 2: Commit**

```
git add CHANGELOG.md
git commit -m "docs: add changelog entry for Docker socket discovery"
```
