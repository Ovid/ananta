# Docker Socket Discovery

## Problem

When a user runs the Document Explorer (or any Ananta app), startup fails
with a massive multi-page stacktrace if the Docker socket is not at the
default path (`/var/run/docker.sock`). This is common on macOS with Docker
Desktop, which places the socket at `~/.docker/run/docker.sock`.

The current code (`_check_docker_available()` in `ananta.py`) catches
`DockerException` and raises `RuntimeError`, but uvicorn's lifespan error
handler dumps the full exception chain. The error message also assumes
Podman when the real issue may be Docker Desktop's non-default socket path.

Related: https://github.com/Ovid/ananta/issues/8

## Goals

1. **Auto-detect the Docker socket** rather than relying on the default path.
2. **Show a clean error message** listing what was tried, not a stacktrace.
3. **Make debugging easier** by showing the discovery steps.

## Design

### Socket Discovery Strategy

`_check_docker_available()` tries these strategies in order:

1. **`DOCKER_HOST` already set** — respect it. Call `docker.from_env()`. If
   it fails, report that the user-specified socket is unreachable (don't
   override their explicit setting).

2. **`docker context inspect`** — run
   `docker context inspect --format '{{.Endpoints.docker.Host}}'` to get
   the socket path from the active Docker CLI context. This is
   authoritative — it's how the Docker CLI itself resolves the socket.
   Any failure (CLI not installed, non-zero exit, unparseable output) is a
   silent fallthrough to step 3 — no warning emitted.

3. **Probe known paths** — check these locations on disk:
   - `/var/run/docker.sock` (Linux default)
   - `~/.docker/run/docker.sock` (Docker Desktop macOS)
   - `~/.colima/default/docker.sock` (Colima)

   Each path is checked with `Path.is_socket()`. If a path exists but is
   not a socket, it is reported in the diagnostic output (e.g.,
   `~/.docker/run/docker.sock — exists but not a socket`).

   When a valid socket is found, set `os.environ["DOCKER_HOST"]` in the
   current process and call `docker.from_env()`. This propagates the
   discovered socket to both `_check_docker_available()` and
   `ContainerExecutor.start()`, which both call `docker.from_env()`.
   Threading `base_url` through four layers was rejected as unnecessary
   plumbing — Ananta owns the process, and each OS process has its own
   environment.

4. **Give up** — raise `RuntimeError` with a clean diagnostic message.

### Error Presentation

When nothing works, the user sees:

```
[ananta] Error: Could not connect to Docker.

  Tried:
    x DOCKER_HOST not set
    x docker context: command not found
    x /var/run/docker.sock — not found
    x ~/.docker/run/docker.sock — exists but not a socket
    x ~/.colima/default/docker.sock — not found

  To fix, either:
    - Start Docker Desktop
    - Set DOCKER_HOST to your Docker socket path
    - If using Podman: export DOCKER_HOST="unix://$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}')"
```

When a socket is found but Docker isn't responding:

```
[ananta] Error: Found Docker socket at ~/.docker/run/docker.sock but Docker is not responding.

  Is Docker Desktop running?
```

The full traceback is logged at `logger.debug()` level for verbose debugging.

### Stacktrace Suppression

In `app_factory.py`, the `lifespan()` function catches `RuntimeError` from
`state.ananta.start()`, prints the message to stderr, and calls
`raise SystemExit(1)`. If uvicorn handles `SystemExit` poorly (logs its
own stacktrace), revisit — but try the simple approach first.

### Code Changes

Three files:

1. **`src/ananta/ananta.py`** — rewrite `_check_docker_available()` with
   the discovery logic. Change from `@staticmethod` to `@classmethod` to
   support a patchable `_KNOWN_SOCKET_PATHS` class attribute.

2. **`src/ananta/experimental/shared/app_factory.py`** — catch
   `RuntimeError` in `lifespan()`, print clean message, exit.

3. **`src/ananta/sandbox/executor.py`** — remove redundant Docker error
   handling from `ContainerExecutor.start()`. Since
   `_check_docker_available()` now runs first and sets `DOCKER_HOST` if
   needed, the executor's `try/except DockerException` around
   `docker.from_env()` is no longer necessary.

### Test Cases

- `DOCKER_HOST` already set — skip discovery, use it
- `docker context inspect` succeeds — use that socket path, set
  `os.environ["DOCKER_HOST"]`
- `docker context inspect` fails — silent fallthrough to path probing for
  each case: CLI not installed, non-zero exit, unparseable/garbage output
- Known path exists and `is_socket()` returns true — use it
- Known path exists but is not a socket — reported in diagnostic, not used
- Nothing found — `RuntimeError` with diagnostic listing what was tried,
  including Podman guidance
- Socket found but daemon not responding — distinct error message
- Existing tests updated to match new discovery behavior and new error
  message format (tests still assert Podman guidance is present)

All discovery logic is in `_check_docker_available()` and testable with
mocked filesystem/subprocess calls.
