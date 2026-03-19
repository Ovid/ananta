"""Docker container executor for sandboxed code execution."""

import json
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import docker
from docker.errors import DockerException
from docker.models.containers import Container

from shesha.sandbox.base import ExecutionResult, LLMQueryHandler
from shesha.security.containers import DEFAULT_SECURITY, ContainerSecurityConfig

__all__ = ["ContainerExecutor", "ExecutionResult", "LLMQueryHandler"]

logger = logging.getLogger(__name__)


class ProtocolError(Exception):
    """Container protocol violation (oversized data, timeout)."""

    pass


class SubcallContentError(Exception):
    """Sub-LLM call rejected (e.g., content exceeds size limit)."""

    pass


# Protocol limits to prevent DoS attacks from malicious containers
MAX_BUFFER_SIZE = 10 * 1024 * 1024  # 10 MB max buffer
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB max incoming message
MAX_READ_DURATION = 300  # 5 min total deadline
MAX_PAYLOAD_SIZE = 50 * 1024 * 1024  # 50 MB max outgoing payload
DEFAULT_SEND_TIMEOUT = 30  # 30 seconds for send operations


class ContainerExecutor:
    """Execute code in a Docker container."""

    def __init__(
        self,
        image: str = "shesha-sandbox",
        memory_limit: str = "512m",
        cpu_count: int = 1,
        llm_query_handler: LLMQueryHandler | None = None,
        security: ContainerSecurityConfig = DEFAULT_SECURITY,
    ) -> None:
        """Initialize executor with container settings."""
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_count = cpu_count
        self.llm_query_handler = llm_query_handler
        self.security = security
        self._client: docker.DockerClient | None = None
        self._container: Container | None = None
        self._socket: Any = None
        self._raw_buffer: bytes = b""  # Buffer for raw Docker stream (with headers)
        self._content_buffer: bytes = b""  # Buffer for demuxed content only

    @property
    def is_alive(self) -> bool:
        """Whether the executor has an active socket connection."""
        return self._socket is not None

    def start(self) -> None:
        """Start a container for execution."""
        logger.debug("Starting container (image=%s, memory=%s)", self.image, self.memory_limit)
        self._raw_buffer = b""  # Clear raw stream buffer
        self._content_buffer = b""  # Clear content buffer
        try:
            self._client = docker.from_env()
        except DockerException as e:
            if "Connection refused" in str(e):
                raise RuntimeError(
                    "Docker is not running. Please start Docker Desktop and try again."
                ) from e
            raise
        self._container = self._client.containers.run(
            self.image,
            detach=True,
            stdin_open=True,
            tty=False,
            mem_limit=self.memory_limit,
            cpu_count=self.cpu_count,
            **self.security.to_docker_kwargs(),
        )
        # Attach to container for bidirectional communication
        self._socket = self._container.attach_socket(params={"stdin": 1, "stdout": 1, "stream": 1})

    def stop(self) -> None:
        """Stop and remove the container."""
        logger.debug("Stopping container")
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._container:
            try:
                self._container.stop(timeout=5)
            except Exception:
                pass  # Container may already be stopped or removed
            try:
                self._container.remove(force=True)
            except Exception:
                pass  # Container may already be removed
            self._container = None
        if self._client:
            self._close_urllib3_pools()
            try:
                self._client.close()
            except Exception:
                pass  # Client may already be closed or daemon unavailable
            self._client = None

    def _close_urllib3_pools(self) -> None:
        """Close urllib3 connection pools inside the Docker client's session.

        ``requests.Session.close()`` calls ``PoolManager.clear()`` which
        drops pool references without calling ``pool.close()``.  Orphaned
        ``http.client.HTTPResponse`` objects then trigger ``ValueError``
        during interpreter shutdown when their finalizer flushes an
        already-closed socket.  Closing each pool explicitly avoids this.
        """
        try:
            for adapter in self._client.api.adapters.values():  # type: ignore[union-attr]
                pool_manager = getattr(adapter, "poolmanager", None)
                if pool_manager is None:
                    continue
                with pool_manager.pools.lock:
                    pools = list(pool_manager.pools._container.values())
                for pool in pools:
                    pool.close()
        except Exception:
            pass  # Best-effort cleanup; don't mask real errors

    def setup_context(self, context: list[str]) -> None:
        """Initialize the context variable in the container."""
        self._send_command({"action": "setup", "context": context})

    def reset_namespace(self) -> dict[str, Any]:
        """Reset the sandbox namespace, clearing user variables but keeping builtins."""
        return self._send_command({"action": "reset"})

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """Execute code in the container, handling llm_query callbacks."""
        # Check if executor is in stopped state (e.g., after protocol error)
        if self._socket is None:
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Executor stopped: no socket connection",
            )

        self._send_message({"action": "execute", "code": code})

        try:
            # Handle responses, which may include llm_query requests
            while True:
                result = self._read_message(timeout=timeout)

                # Check if this is an llm_query request
                if result.get("action") == "llm_query":
                    if self.llm_query_handler is None:
                        # No handler — signal error so sandbox raises ValueError
                        self._send_message(
                            {
                                "action": "llm_response",
                                "error": "No LLM query handler configured",
                            }
                        )
                    else:
                        # Call handler and send response back
                        try:
                            llm_response = self.llm_query_handler(
                                result["instruction"],
                                result["content"],
                            )
                        except SubcallContentError as e:
                            # Content rejected — send error so sandbox raises
                            self._send_message(
                                {
                                    "action": "llm_response",
                                    "error": str(e),
                                }
                            )
                        except (KeyError, UnicodeDecodeError):
                            raise  # Protocol violations — handled by outer except
                        except Exception as e:
                            # LLM call failed (timeout, transient error, etc.)
                            # Send error back to sandbox so the model can adapt
                            # instead of crashing the executor.
                            self._send_message(
                                {
                                    "action": "llm_response",
                                    "error": f"LLM call failed: {e}",
                                }
                            )
                        else:
                            self._send_message(
                                {
                                    "action": "llm_response",
                                    "result": llm_response,
                                }
                            )
                    continue

                # Check if this is a batched llm_query request
                if result.get("action") == "llm_query_batch":
                    if self.llm_query_handler is None:
                        self._send_message(
                            {
                                "action": "llm_batch_response",
                                "error": "No LLM query handler configured",
                            }
                        )
                    else:
                        prompts = result["prompts"]
                        results_list = self._execute_batch(prompts)
                        self._send_message(
                            {
                                "action": "llm_batch_response",
                                "results": results_list,
                            }
                        )
                    continue

                # This is the final execution result
                return ExecutionResult(
                    status=result.get("status", "error"),
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    return_value=result.get("return_value"),
                    error=result.get("error"),
                    final_answer=result.get("final_answer"),
                    final_var=result.get("final_var"),
                    final_value=result.get("final_value"),
                    vars=result.get("vars"),
                )
        except ProtocolError as e:
            # Protocol violation implies potentially malicious/broken container state.
            # Terminate it to prevent reuse of compromised container.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: {e}",
            )
        except json.JSONDecodeError as e:
            # Invalid JSON from container (e.g., sandbox wrote to sys.__stdout__).
            # Treat as protocol violation - container is in unknown state.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: invalid JSON from container: {e}",
            )
        except KeyError as e:
            # Malformed message missing required fields (e.g., llm_query without
            # instruction/content). Treat as protocol violation.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: missing required field {e}",
            )
        except UnicodeDecodeError as e:
            # Non-UTF8 bytes from container (e.g., writing to sys.stdout.buffer).
            # Treat as protocol violation - container is sending invalid data.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: invalid UTF-8 from container: {e}",
            )
        except RuntimeError as e:
            # Container was stopped externally (e.g., pool.stop() during
            # in-flight query). Return error so the engine can recover.
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Executor stopped: {e}",
            )

    _MAX_BATCH_WORKERS = 32

    def _execute_batch(self, prompts: list[str]) -> list[str]:
        """Execute batch of LLM prompts concurrently via thread pool."""
        if not prompts:
            return []

        handler = self.llm_query_handler
        assert handler is not None

        def _call_one(prompt: str) -> str:
            try:
                return handler(prompt, "")
            except SubcallContentError as e:
                return f"[error: {e}]"

        workers = min(len(prompts), self._MAX_BATCH_WORKERS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_call_one, prompts))

    def _send_message(self, data: dict[str, Any], timeout: int = DEFAULT_SEND_TIMEOUT) -> None:
        """Send a length-prefixed JSON message to container stdin."""
        payload = json.dumps(data).encode("utf-8")
        if len(payload) > MAX_PAYLOAD_SIZE:
            raise ProtocolError(f"Payload size {len(payload)} exceeds maximum {MAX_PAYLOAD_SIZE}")
        frame = struct.pack(">I", len(payload)) + payload
        if self._socket is not None:
            sock = self._socket._sock
            previous_timeout = sock.gettimeout()
            sock.settimeout(timeout)
            try:
                sock.sendall(frame)
            except OSError as e:
                raise ProtocolError(f"Send failed: {e}") from e
            finally:
                sock.settimeout(previous_timeout)

    def _read_message(self, timeout: int = 30) -> dict[str, Any]:
        """Read a length-prefixed JSON message from container stdout.

        Docker attach socket demuxing (8-byte headers) fills _content_buffer.
        After demuxing, reads 4-byte BE length prefix + exact payload from buffer.

        Uses two separate buffers:
        - _raw_buffer: raw Docker stream data (may contain headers)
        - _content_buffer: demuxed payload content only
        """
        if self._socket is None:
            raise RuntimeError("No socket connection")

        self._socket._sock.settimeout(timeout)

        # Effective deadline: the shorter of MAX_READ_DURATION and timeout + 10s buffer.
        effective_deadline = min(MAX_READ_DURATION, timeout + 10)
        start_time = time.monotonic()

        while True:
            if time.monotonic() - start_time > effective_deadline:
                raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")

            # Check if we have a complete length-prefixed message in content buffer
            if len(self._content_buffer) >= 4:
                msg_len = struct.unpack(">I", self._content_buffer[:4])[0]
                if msg_len > MAX_MESSAGE_SIZE:
                    raise ProtocolError(
                        f"Message size {msg_len} exceeds maximum {MAX_MESSAGE_SIZE}"
                    )
                if len(self._content_buffer) >= 4 + msg_len:
                    payload = self._content_buffer[4 : 4 + msg_len]
                    self._content_buffer = self._content_buffer[4 + msg_len :]
                    result: dict[str, Any] = json.loads(payload.decode("utf-8"))
                    return result

            # Need more content - demux from raw buffer or read more data
            self._demux_docker_frame(start_time, effective_deadline)

    def _demux_docker_frame(self, start_time: float, effective_deadline: float) -> None:
        """Demux one Docker frame from _raw_buffer into _content_buffer.

        Reads from socket as needed. Raises ProtocolError on limits/deadline.
        """
        # Ensure we have at least 8 bytes for a Docker header
        while len(self._raw_buffer) < 8:
            if time.monotonic() - start_time > effective_deadline:
                raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")
            chunk = self._socket._sock.recv(4096)
            if not chunk:
                raise ProtocolError("Connection closed before message complete")
            self._raw_buffer += chunk
            if len(self._raw_buffer) > MAX_BUFFER_SIZE:
                raise ProtocolError(f"Raw buffer exceeded {MAX_BUFFER_SIZE} bytes")

        # Check if this looks like a Docker header
        if self._raw_buffer[0] in (1, 2) and self._raw_buffer[1:4] == b"\x00\x00\x00":
            # Extract payload length from bytes 4-7 (big-endian)
            payload_len = int.from_bytes(self._raw_buffer[4:8], "big")

            # Read until we have the full frame (header + payload)
            while len(self._raw_buffer) < 8 + payload_len:
                if time.monotonic() - start_time > effective_deadline:
                    raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")
                chunk = self._socket._sock.recv(4096)
                if not chunk:
                    raise ProtocolError("Connection closed before message complete")
                self._raw_buffer += chunk
                if len(self._raw_buffer) > MAX_BUFFER_SIZE:
                    raise ProtocolError(f"Raw buffer exceeded {MAX_BUFFER_SIZE} bytes")

            # Extract payload and remove the frame from raw buffer
            payload = self._raw_buffer[8 : 8 + payload_len]
            self._raw_buffer = self._raw_buffer[8 + payload_len :]

            # Append payload to content buffer
            self._content_buffer += payload
            if len(self._content_buffer) > MAX_BUFFER_SIZE:
                raise ProtocolError(f"Content buffer exceeded {MAX_BUFFER_SIZE} bytes")
        else:
            # Not a Docker header - treat raw buffer as plain data
            self._content_buffer += self._raw_buffer
            self._raw_buffer = b""
            if len(self._content_buffer) > MAX_BUFFER_SIZE:
                raise ProtocolError(f"Content buffer exceeded {MAX_BUFFER_SIZE} bytes")

    def _send_command(self, command: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        """Send a JSON command to the container and get response."""
        self._send_message(command)
        return self._read_message(timeout=timeout)

    def __enter__(self) -> "ContainerExecutor":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.stop()
