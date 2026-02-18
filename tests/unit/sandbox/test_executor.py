"""Tests for sandbox executor."""

import json
import struct
import time
from unittest.mock import MagicMock, patch

import pytest

from shesha.sandbox.executor import ContainerExecutor, ExecutionResult
from shesha.security.containers import ContainerSecurityConfig


class TestProtocolError:
    """Tests for ProtocolError exception."""

    def test_protocol_error_exists(self):
        """ProtocolError is importable from executor module."""
        from shesha.sandbox.executor import ProtocolError

        err = ProtocolError("test message")
        assert str(err) == "test message"


class TestSubcallContentError:
    """Tests for SubcallContentError exception."""

    def test_subcall_content_error_exists(self):
        """SubcallContentError is importable from executor module."""
        from shesha.sandbox.executor import SubcallContentError

        err = SubcallContentError("content too large")
        assert str(err) == "content too large"

    def test_subcall_content_error_is_exception(self):
        """SubcallContentError is a proper Exception subclass."""
        from shesha.sandbox.executor import SubcallContentError

        assert issubclass(SubcallContentError, Exception)


class TestProtocolLimits:
    """Tests for protocol limit constants."""

    def test_max_buffer_size_exists(self):
        """MAX_BUFFER_SIZE constant is defined."""
        from shesha.sandbox.executor import MAX_BUFFER_SIZE

        assert MAX_BUFFER_SIZE == 10 * 1024 * 1024  # 10 MB

    def test_max_message_size_exists(self):
        """MAX_MESSAGE_SIZE constant is defined."""
        from shesha.sandbox.executor import MAX_MESSAGE_SIZE

        assert MAX_MESSAGE_SIZE == 10 * 1024 * 1024  # 10 MB

    def test_max_read_duration_exists(self):
        """MAX_READ_DURATION constant is defined."""
        from shesha.sandbox.executor import MAX_READ_DURATION

        assert MAX_READ_DURATION == 300  # 5 minutes


def make_docker_frame(data: bytes, stream_type: int = 1) -> bytes:
    """Create a Docker multiplexed stream frame.

    Docker attach socket uses 8-byte header:
    - 1 byte: stream type (1=stdout, 2=stderr)
    - 3 bytes: padding (zeros)
    - 4 bytes: payload length (big-endian)
    """
    header = bytes([stream_type, 0, 0, 0]) + len(data).to_bytes(4, "big")
    return header + data


def make_length_prefixed(data: dict) -> bytes:
    """Create a 4-byte length-prefixed JSON message (container protocol framing)."""
    payload = json.dumps(data).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class TestDockerFrameParsing:
    """Tests for Docker multiplexed stream parsing in _read_message."""

    def test_read_message_parses_single_docker_frame(self):
        """_read_message reads a complete length-prefixed message from one Docker frame."""
        data = {"status": "ok", "data": "some value"}
        msg_bytes = make_length_prefixed(data)
        stream_data = make_docker_frame(msg_bytes)

        mock_socket = MagicMock()
        chunks = [stream_data]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        result = executor._read_message(timeout=5)
        assert result == data

    def test_read_message_handles_split_across_docker_frames(self):
        """_read_message handles message split across multiple Docker frames.

        Length prefix in first Docker frame, JSON payload in second.
        """
        data = {"status": "ok", "content": "A" * 1000}
        payload = json.dumps(data).encode("utf-8")
        length_prefix = struct.pack(">I", len(payload))

        # Split: length prefix in one Docker frame, payload in another
        stream_data = make_docker_frame(length_prefix) + make_docker_frame(payload)

        mock_socket = MagicMock()
        chunks = [stream_data]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        result = executor._read_message(timeout=5)
        assert result == data

    def test_read_message_handles_multiple_messages_in_one_frame(self):
        """_read_message reads first message, leaves second in buffer."""
        msg1 = {"status": "ok", "seq": 1}
        msg2 = {"status": "ok", "seq": 2}
        combined = make_length_prefixed(msg1) + make_length_prefixed(msg2)
        stream_data = make_docker_frame(combined)

        mock_socket = MagicMock()
        chunks = [stream_data]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        result1 = executor._read_message(timeout=5)
        assert result1 == msg1

        # Second message should be readable from buffer
        result2 = executor._read_message(timeout=5)
        assert result2 == msg2

    def test_read_message_handles_large_payload(self):
        """_read_message handles payloads where Docker frame length field contains 0x80+ bytes."""
        # Large payload that causes Docker frame length > 0x8000
        data = {"result": "x" * 40000}
        msg_bytes = make_length_prefixed(data)
        stream_data = make_docker_frame(msg_bytes)

        mock_socket = MagicMock()
        chunks = [stream_data]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        result = executor._read_message(timeout=5)
        assert result == data


class TestConnectionClose:
    """Tests for connection close handling in _read_message."""

    def test_read_message_raises_on_connection_close_before_length_prefix(self):
        """_read_message raises ProtocolError when connection closes before length prefix."""
        from shesha.sandbox.executor import ProtocolError

        mock_socket = MagicMock()

        # Send only 2 bytes (not enough for 4-byte length prefix), then close
        chunks = [b"\x00\x00", b""]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        with pytest.raises(ProtocolError, match="Connection closed"):
            executor._read_message(timeout=5)

    def test_read_message_raises_on_connection_close_mid_payload(self):
        """_read_message raises ProtocolError when connection closes mid-payload."""
        from shesha.sandbox.executor import ProtocolError

        mock_socket = MagicMock()

        # Send a length prefix saying 100 bytes, but only deliver 10 bytes then close
        partial = struct.pack(">I", 100) + b"x" * 10
        frame = make_docker_frame(partial)
        chunks = [frame, b""]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        with pytest.raises(ProtocolError, match="Connection closed"):
            executor._read_message(timeout=5)


class TestBufferLimits:
    """Tests for buffer size limits in _read_message."""

    def test_read_message_raises_on_oversized_content_buffer(self):
        """_read_message raises ProtocolError when content buffer exceeds limit."""
        from shesha.sandbox.executor import MAX_BUFFER_SIZE, ProtocolError

        mock_socket = MagicMock()
        # Send Docker frames with data that would exceed MAX_BUFFER_SIZE
        chunk_size = 1024 * 1024  # 1 MB chunks
        chunks_needed = (MAX_BUFFER_SIZE // chunk_size) + 2

        chunk_data = [make_docker_frame(b"x" * chunk_size) for _ in range(chunks_needed)]
        chunk_iter = iter(chunk_data)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        with pytest.raises(ProtocolError) as exc_info:
            executor._read_message(timeout=5)

        error_msg = str(exc_info.value).lower()
        assert "buffer" in error_msg or "message" in error_msg


class TestContainerExecutor:
    """Tests for ContainerExecutor."""

    def test_execution_result_dataclass(self):
        """ExecutionResult stores execution output."""
        result = ExecutionResult(
            status="ok",
            stdout="Hello",
            stderr="",
            return_value=None,
            error=None,
            final_answer=None,
        )
        assert result.status == "ok"
        assert result.stdout == "Hello"

    @patch("shesha.sandbox.executor.docker")
    def test_executor_creates_container(self, mock_docker: MagicMock):
        """Executor creates a Docker container."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()

        mock_client.containers.run.assert_called_once()
        assert executor._container is not None

    @patch("shesha.sandbox.executor.docker")
    def test_executor_stops_container(self, mock_docker: MagicMock):
        """Executor stops and removes container on stop()."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()
        executor.stop()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()

    @patch("shesha.sandbox.executor.docker")
    def test_executor_closes_docker_client_on_stop(self, mock_docker: MagicMock):
        """Executor closes the DockerClient on stop() to prevent resource leaks.

        The DockerClient maintains HTTP connections to the Docker daemon.
        If not closed, the urllib3 HTTP response finalizer will fail on exit.
        """
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()
        executor.stop()

        # DockerClient.close() must be called to prevent urllib3 errors on exit
        mock_client.close.assert_called_once()

    @patch("shesha.sandbox.executor.docker")
    def test_executor_closes_urllib3_pools_on_stop(self, mock_docker: MagicMock):
        """Executor closes urllib3 connection pools before closing DockerClient.

        requests.Session.close() calls PoolManager.clear() which drops pool
        references without calling pool.close().  Orphaned HTTPResponse objects
        then trigger ValueError during interpreter shutdown.  Explicitly closing
        each pool first prevents this.
        """
        mock_pool = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.poolmanager.pools.lock = MagicMock()
        mock_adapter.poolmanager.pools._container = {"key": mock_pool}

        mock_client = MagicMock()
        mock_client.api.adapters = {"https://": mock_adapter}
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()
        executor.stop()

        mock_pool.close.assert_called_once()

    @patch("shesha.sandbox.executor.docker")
    def test_start_raises_clear_error_when_docker_not_running(self, mock_docker: MagicMock):
        """Executor provides clear error message when Docker daemon is not running.

        When docker.from_env() fails with ConnectionRefusedError (wrapped in
        docker.errors.DockerException), the error message should clearly explain
        that Docker Desktop needs to be started.
        """
        from docker.errors import DockerException

        # Simulate Docker daemon not running
        mock_docker.from_env.side_effect = DockerException(
            "Error while fetching server API version: "
            "('Connection aborted.', ConnectionRefusedError(61, 'Connection refused'))"
        )

        executor = ContainerExecutor()

        import pytest

        with pytest.raises(RuntimeError) as exc_info:
            executor.start()

        error_msg = str(exc_info.value)
        assert "Docker" in error_msg
        assert "not running" in error_msg or "start" in error_msg.lower()


class TestContainerSecurityIntegration:
    """Tests for container security integration."""

    @patch("shesha.sandbox.executor.docker")
    def test_executor_uses_default_security(self, mock_docker: MagicMock) -> None:
        """Executor applies default security config."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor()
        executor.start()

        # Verify security kwargs were passed
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["cap_drop"] == ["ALL"]
        assert call_kwargs["privileged"] is False
        assert call_kwargs["read_only"] is True
        assert "no-new-privileges:true" in call_kwargs["security_opt"]

        executor.stop()

    @patch("shesha.sandbox.executor.docker")
    def test_executor_accepts_custom_security(self, mock_docker: MagicMock) -> None:
        """Executor accepts custom security config."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        custom_security = ContainerSecurityConfig(cap_drop=["NET_ADMIN"])
        executor = ContainerExecutor(security=custom_security)
        executor.start()

        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["cap_drop"] == ["NET_ADMIN"]

        executor.stop()


class TestMessageSizeLimit:
    """Tests for message size limit in _read_message."""

    def test_read_message_raises_on_oversized_message(self):
        """_read_message raises ProtocolError when message exceeds MAX_MESSAGE_SIZE."""
        from shesha.sandbox.executor import (
            MAX_MESSAGE_SIZE,
            ContainerExecutor,
            ProtocolError,
        )

        mock_socket = MagicMock()

        # Send a length prefix declaring a message larger than MAX_MESSAGE_SIZE
        oversized_length = struct.pack(">I", MAX_MESSAGE_SIZE + 100)
        frame = make_docker_frame(oversized_length)

        chunks = [frame]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        with pytest.raises(ProtocolError) as exc_info:
            executor._read_message(timeout=5)

        assert "message" in str(exc_info.value).lower() or "size" in str(exc_info.value).lower()


class TestReadDeadline:
    """Tests for overall deadline in _read_message."""

    def test_read_message_raises_on_deadline_exceeded(self):
        """_read_message raises ProtocolError when total time exceeds deadline."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        mock_socket = MagicMock()

        # Simulate slow drip that would exceed deadline
        call_count = 0

        def mock_recv(size):
            nonlocal call_count
            call_count += 1
            # Return small Docker-framed chunks (not enough for a complete message)
            if call_count < 100:
                return make_docker_frame(b"x")
            return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        start_time = time.monotonic()
        call_sequence = [start_time, start_time + 301]
        time_iter = iter(call_sequence)

        def mock_monotonic():
            try:
                return next(time_iter)
            except StopIteration:
                return start_time + 400

        with patch("shesha.sandbox.executor.time.monotonic", mock_monotonic):
            with pytest.raises(ProtocolError) as exc_info:
                executor._read_message(timeout=5)

        assert (
            "duration" in str(exc_info.value).lower() or "deadline" in str(exc_info.value).lower()
        )

    def test_read_message_enforces_deadline_in_inner_frame_loop(self):
        """_read_message enforces deadline inside Docker frame reading loop.

        A malicious container could drip data slowly to keep the inner loop spinning.
        """
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        mock_socket = MagicMock()

        # Simulate a large Docker frame that drips in slowly
        header = bytes([1, 0, 0, 0, 0, 0, 0x27, 0x10])  # stream=1, length=10000
        recv_count = 0

        def mock_recv(size):
            nonlocal recv_count
            recv_count += 1
            if recv_count == 1:
                return header
            return b"x" * 10

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        start_time = 1000.0
        monotonic_calls = 0

        def mock_monotonic():
            nonlocal monotonic_calls
            monotonic_calls += 1
            if monotonic_calls <= 2:
                return start_time
            return start_time + 301

        with patch("shesha.sandbox.executor.time.monotonic", mock_monotonic):
            with pytest.raises(ProtocolError) as exc_info:
                executor._read_message(timeout=5)

        assert "duration" in str(exc_info.value).lower()


class TestExecuteProtocolHandling:
    """Tests for ProtocolError handling in execute()."""

    def test_execute_returns_error_result_on_protocol_error(self):
        """execute() returns error ExecutionResult when ProtocolError occurs."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        # Mock _read_message to raise ProtocolError
        with patch.object(executor, "_read_message", side_effect=ProtocolError("buffer overflow")):
            with patch.object(executor, "_send_message"):
                result = executor.execute("print('hello')")

        assert result.status == "error"
        assert "protocol" in result.error.lower() or "buffer" in result.error.lower()

    def test_execute_stops_container_on_protocol_error(self):
        """execute() stops the container when ProtocolError occurs."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        with patch.object(executor, "_read_message", side_effect=ProtocolError("malicious data")):
            with patch.object(executor, "_send_message"):
                with patch.object(executor, "stop") as mock_stop:
                    executor.execute("print('hello')")

        mock_stop.assert_called_once()

    def test_execute_handles_malformed_llm_query_as_protocol_error(self):
        """execute() treats llm_query missing required fields as protocol violation."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()
        executor._socket = MagicMock()
        executor.llm_query_handler = MagicMock()

        # Malformed llm_query - missing 'instruction' and 'content' fields
        malformed_response = {"action": "llm_query"}

        with patch.object(executor, "_read_message", return_value=malformed_response):
            with patch.object(executor, "_send_message"):
                with patch.object(executor, "stop") as mock_stop:
                    result = executor.execute("print('hello')")

        assert result.status == "error"
        assert "protocol" in result.error.lower() or "missing" in result.error.lower()
        mock_stop.assert_called_once()

    def test_execute_returns_error_when_socket_is_none(self):
        """execute() returns error result when called after stop() (no socket)."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()
        # Simulate stopped state - socket is None
        executor._socket = None

        result = executor.execute("print('hello')")

        # Should return error result, not raise RuntimeError
        assert result.status == "error"
        assert "stopped" in result.error.lower() or "socket" in result.error.lower()


class TestSubcallContentErrorHandling:
    """Tests for SubcallContentError handling in execute()."""

    def test_execute_sends_error_response_on_subcall_content_error(self):
        """execute() sends error field to sandbox when handler raises SubcallContentError."""

        from shesha.sandbox.executor import SubcallContentError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        error_msg = "Content size (735,490 chars) exceeds the sub-LLM limit"

        def handler_raises(instruction: str, content: str) -> str:
            raise SubcallContentError(error_msg)

        executor.llm_query_handler = handler_raises

        # Simulate: container sends llm_query, then receives error response, then sends result
        llm_query_msg = {
            "action": "llm_query",
            "instruction": "summarize",
            "content": "big content",
        }
        # After sending error response, container code raises ValueError and returns error result
        exec_result_msg = {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "error": "ValueError: " + error_msg,
        }

        read_responses = iter([llm_query_msg, exec_result_msg])

        with patch.object(executor, "_read_message", side_effect=read_responses):
            sent_data: list[dict] = []
            with patch.object(
                executor, "_send_message", side_effect=lambda d, **kw: sent_data.append(d)
            ):
                executor.execute("analysis = llm_query('summarize', big_content)")

        # First _send_message is the execute command, second is the error response
        assert len(sent_data) == 2
        error_response = sent_data[1]
        assert error_response["action"] == "llm_response"
        assert "error" in error_response
        assert error_msg in error_response["error"]

    def test_execute_does_not_stop_container_on_subcall_content_error(self):
        """SubcallContentError does not kill the container — user error."""

        from shesha.sandbox.executor import SubcallContentError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        def handler_raises(instruction: str, content: str) -> str:
            raise SubcallContentError("too large")

        executor.llm_query_handler = handler_raises

        llm_query_msg = {"action": "llm_query", "instruction": "x", "content": "y"}
        exec_result_msg = {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "error": "ValueError: too large",
        }

        with patch.object(executor, "_read_message", side_effect=[llm_query_msg, exec_result_msg]):
            with patch.object(executor, "_send_message"):
                with patch.object(executor, "stop") as mock_stop:
                    executor.execute("llm_query('x', 'y')")

        # Container should NOT be stopped — this is a content error, not protocol violation
        mock_stop.assert_not_called()


class TestNoHandlerErrorProtocol:
    """Tests for llm_query when no handler is configured."""

    def test_no_handler_sends_error_field_not_result(self):
        """When llm_query_handler is None, executor sends error field to sandbox."""

        executor = ContainerExecutor()
        executor._socket = MagicMock()
        executor.llm_query_handler = None

        llm_query_msg = {"action": "llm_query", "instruction": "summarize", "content": "data"}
        exec_result_msg = {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "error": "ValueError: No LLM query handler configured",
        }

        read_responses = iter([llm_query_msg, exec_result_msg])

        with patch.object(executor, "_read_message", side_effect=read_responses):
            sent_data: list[dict] = []
            with patch.object(
                executor, "_send_message", side_effect=lambda d, **kw: sent_data.append(d)
            ):
                executor.execute("llm_query('summarize', 'data')")

        # Second _send_message should be the llm_response with error field
        assert len(sent_data) == 2
        error_response = sent_data[1]
        assert error_response["action"] == "llm_response"
        assert "error" in error_response
        assert "result" not in error_response


class TestIsAlive:
    """Tests for is_alive property."""

    def test_is_alive_true_when_socket_exists(self):
        """is_alive returns True when socket is set."""
        executor = ContainerExecutor()
        executor._socket = MagicMock()

        assert executor.is_alive is True

    def test_is_alive_false_when_socket_is_none(self):
        """is_alive returns False when socket is None."""
        executor = ContainerExecutor()
        executor._socket = None

        assert executor.is_alive is False

    def test_is_alive_false_after_protocol_error(self):
        """is_alive returns False after ProtocolError kills executor."""
        from shesha.sandbox.executor import ProtocolError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        # Simulate protocol error during execute (which calls stop())
        with patch.object(executor, "_read_message", side_effect=ProtocolError("overflow")):
            with patch.object(executor, "_send_message"):
                executor.execute("print('hello')")

        # stop() sets _socket = None
        assert executor.is_alive is False


class TestSendTimeout:
    """Tests for send timeout on _send_message."""

    def test_send_message_sets_socket_timeout(self):
        """_send_message sets a timeout on the socket before sending."""
        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.gettimeout.return_value = 30.0
        executor._socket = mock_socket

        executor._send_message({"action": "ping"}, timeout=10)

        # First settimeout sets send timeout, second restores previous
        calls = mock_socket._sock.settimeout.call_args_list
        assert calls[0][0][0] == 10
        mock_socket._sock.sendall.assert_called_once()

    def test_send_message_uses_default_timeout(self):
        """_send_message uses default timeout when none specified."""
        from shesha.sandbox.executor import DEFAULT_SEND_TIMEOUT

        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.gettimeout.return_value = 30.0
        executor._socket = mock_socket

        executor._send_message({"action": "ping"})

        calls = mock_socket._sock.settimeout.call_args_list
        # First call sets send timeout (default), second restores previous
        assert calls[0][0][0] == DEFAULT_SEND_TIMEOUT
        assert DEFAULT_SEND_TIMEOUT > 0


class TestPayloadSizeLimit:
    """Tests for payload size limit on _send_message."""

    def test_send_message_rejects_oversized_payload(self):
        """_send_message raises ProtocolError when payload exceeds MAX_PAYLOAD_SIZE."""
        from shesha.sandbox.executor import MAX_PAYLOAD_SIZE, ProtocolError

        executor = ContainerExecutor()
        mock_socket = MagicMock()
        executor._socket = mock_socket

        oversized_data = {"data": "x" * (MAX_PAYLOAD_SIZE + 100)}

        with pytest.raises(ProtocolError, match="[Pp]ayload"):
            executor._send_message(oversized_data)

        # Should not have sent anything
        mock_socket._sock.sendall.assert_not_called()

    def test_max_payload_size_constant_exists(self):
        """MAX_PAYLOAD_SIZE constant is defined."""
        from shesha.sandbox.executor import MAX_PAYLOAD_SIZE

        assert MAX_PAYLOAD_SIZE == 50 * 1024 * 1024  # 50 MB


class TestSendMessageLengthPrefix:
    """Tests for length-prefix framing in _send_message."""

    def test_send_message_prepends_length_prefix(self):
        """_send_message sends 4-byte BE length prefix + JSON payload."""
        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.gettimeout.return_value = 30.0
        executor._socket = mock_socket

        data = {"action": "execute", "code": "print('hello')"}
        executor._send_message(data)

        sent_bytes = mock_socket._sock.sendall.call_args[0][0]
        expected_payload = json.dumps(data).encode("utf-8")
        expected_frame = struct.pack(">I", len(expected_payload)) + expected_payload
        assert sent_bytes == expected_frame


class TestSendMessageSocketErrors:
    """Tests for socket error handling in _send_message."""

    def test_send_message_wraps_os_error_as_protocol_error(self):
        """_send_message wraps OSError from sendall as ProtocolError."""
        from shesha.sandbox.executor import ProtocolError

        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.sendall.side_effect = OSError("Connection reset")
        executor._socket = mock_socket

        with pytest.raises(ProtocolError, match="Connection reset"):
            executor._send_message({"action": "ping"})

    def test_send_message_wraps_timeout_error_as_protocol_error(self):
        """_send_message wraps TimeoutError from sendall as ProtocolError."""
        from shesha.sandbox.executor import ProtocolError

        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.sendall.side_effect = TimeoutError("Send timed out")
        executor._socket = mock_socket

        with pytest.raises(ProtocolError, match="Send timed out"):
            executor._send_message({"action": "ping"})

    def test_send_message_restores_previous_timeout(self):
        """_send_message restores the previous socket timeout after sending."""
        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.gettimeout.return_value = 30.0
        executor._socket = mock_socket

        executor._send_message({"action": "ping"}, timeout=5)

        # Should restore previous timeout after send
        calls = mock_socket._sock.settimeout.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == 5  # Set send timeout
        assert calls[1][0][0] == 30.0  # Restore previous

    def test_send_message_restores_timeout_on_error(self):
        """_send_message restores the previous timeout even when sendall fails."""
        from shesha.sandbox.executor import ProtocolError

        executor = ContainerExecutor()
        mock_socket = MagicMock()
        mock_socket._sock.gettimeout.return_value = 30.0
        mock_socket._sock.sendall.side_effect = OSError("Broken pipe")
        executor._socket = mock_socket

        with pytest.raises(ProtocolError):
            executor._send_message({"action": "ping"}, timeout=5)

        # Should still restore previous timeout
        calls = mock_socket._sock.settimeout.call_args_list
        assert len(calls) == 2
        assert calls[1][0][0] == 30.0


class TestEffectiveDeadline:
    """Tests for deadline tied to execution timeout."""

    def test_read_message_deadline_respects_execution_timeout(self):
        """_read_message deadline is bounded by timeout parameter, not just MAX_READ_DURATION."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        mock_socket = MagicMock()

        call_count = [0]

        def mock_recv(size):
            call_count[0] += 1
            if call_count[0] < 100:
                return make_docker_frame(b"x")
            return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        start_time = 1000.0
        mono_calls = [0]

        def mock_monotonic():
            mono_calls[0] += 1
            if mono_calls[0] <= 2:
                return start_time
            return start_time + 16  # 16s exceeds effective deadline of 15s (5+10)

        with patch("shesha.sandbox.executor.time.monotonic", mock_monotonic):
            with pytest.raises(ProtocolError):
                executor._read_message(timeout=5)


class TestBatchedLlmQuery:
    """Tests for llm_query_batch handling in execute()."""

    def test_execute_handles_batch_request(self):
        """execute() dispatches llm_query_batch prompts through handler."""
        executor = ContainerExecutor()
        executor._socket = MagicMock()

        call_log: list[tuple[str, str]] = []

        def mock_handler(instruction: str, content: str) -> str:
            call_log.append((instruction, content))
            return f"result for: {instruction}"

        executor.llm_query_handler = mock_handler

        batch_msg = {
            "action": "llm_query_batch",
            "prompts": ["classify: cat", "classify: dog"],
        }
        exec_result_msg = {
            "status": "ok",
            "stdout": "done\n",
            "stderr": "",
            "return_value": None,
            "error": None,
        }

        read_responses = iter([batch_msg, exec_result_msg])

        with patch.object(executor, "_read_message", side_effect=read_responses):
            sent_data: list[dict] = []
            with patch.object(
                executor, "_send_message", side_effect=lambda d, **kw: sent_data.append(d)
            ):
                executor.execute("llm_query_batched(['classify: cat', 'classify: dog'])")

        assert len(sent_data) == 2
        batch_response = sent_data[1]
        assert batch_response["action"] == "llm_batch_response"
        assert len(batch_response["results"]) == 2

    def test_execute_batch_runs_concurrently(self):
        """execute() dispatches batch prompts concurrently, not sequentially."""
        import threading

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        thread_ids: list[int] = []
        barrier = threading.Barrier(4, timeout=5)

        def slow_handler(instruction: str, content: str) -> str:
            thread_ids.append(threading.current_thread().ident)
            barrier.wait()
            return f"result for: {instruction}"

        executor.llm_query_handler = slow_handler

        batch_msg = {
            "action": "llm_query_batch",
            "prompts": [f"prompt_{i}" for i in range(4)],
        }
        exec_result_msg = {
            "status": "ok",
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "error": None,
        }

        read_responses = iter([batch_msg, exec_result_msg])

        with patch.object(executor, "_read_message", side_effect=read_responses):
            sent_data: list[dict] = []
            with patch.object(
                executor, "_send_message", side_effect=lambda d, **kw: sent_data.append(d)
            ):
                executor.execute("llm_query_batched([...])")

        assert len(thread_ids) == 4
        assert len(set(thread_ids)) >= 2

    def test_execute_batch_preserves_order(self):
        """Batch results are returned in same order as input prompts."""
        executor = ContainerExecutor()
        executor._socket = MagicMock()

        def ordered_handler(instruction: str, content: str) -> str:
            return f"answer_{instruction}"

        executor.llm_query_handler = ordered_handler

        prompts = [f"q{i}" for i in range(5)]
        batch_msg = {"action": "llm_query_batch", "prompts": prompts}
        exec_result_msg = {
            "status": "ok",
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "error": None,
        }

        read_responses = iter([batch_msg, exec_result_msg])

        with patch.object(executor, "_read_message", side_effect=read_responses):
            sent_data: list[dict] = []
            with patch.object(
                executor, "_send_message", side_effect=lambda d, **kw: sent_data.append(d)
            ):
                executor.execute("llm_query_batched([...])")

        batch_response = sent_data[1]
        results = batch_response["results"]
        assert results == [f"answer_q{i}" for i in range(5)]

    def test_execute_batch_sends_error_on_no_handler(self):
        """execute() sends error when llm_query_batch is received with no handler."""
        executor = ContainerExecutor()
        executor._socket = MagicMock()
        executor.llm_query_handler = None

        batch_msg = {"action": "llm_query_batch", "prompts": ["prompt1"]}
        exec_result_msg = {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "return_value": None,
            "error": "ValueError: No LLM query handler configured",
        }

        read_responses = iter([batch_msg, exec_result_msg])

        with patch.object(executor, "_read_message", side_effect=read_responses):
            sent_data: list[dict] = []
            with patch.object(
                executor, "_send_message", side_effect=lambda d, **kw: sent_data.append(d)
            ):
                executor.execute("llm_query_batched(['prompt1'])")

        batch_response = sent_data[1]
        assert batch_response["action"] == "llm_batch_response"
        assert "error" in batch_response


class TestBatchExecution:
    """Tests for _execute_batch on ContainerExecutor."""

    def test_execute_batch_empty_prompts_returns_empty_list(self):
        """_execute_batch returns [] immediately for an empty prompts list."""
        executor = ContainerExecutor()
        executor.llm_query_handler = lambda inst, cont: "should not be called"

        result = executor._execute_batch([])
        assert result == []

    def test_execute_batch_caps_thread_count(self):
        """_execute_batch caps max_workers to avoid unbounded thread creation."""
        from concurrent.futures import ThreadPoolExecutor

        executor = ContainerExecutor()
        executor.llm_query_handler = lambda inst, cont: "ok"

        captured_max_workers: list[int] = []
        _real_init = ThreadPoolExecutor.__init__

        def _capturing_init(self_tpe, *args, **kwargs):
            captured_max_workers.append(kwargs.get("max_workers", args[0] if args else None))
            _real_init(self_tpe, *args, **kwargs)

        with patch.object(ThreadPoolExecutor, "__init__", _capturing_init):
            result = executor._execute_batch([f"p{i}" for i in range(100)])

        assert len(result) == 100
        assert captured_max_workers[0] <= 32, (
            f"max_workers should be capped, got {captured_max_workers[0]}"
        )


class TestExecutionResultVars:
    """Tests for vars field on ExecutionResult."""

    def test_execution_result_vars_field(self) -> None:
        """ExecutionResult has an optional vars field."""
        result = ExecutionResult(
            status="ok",
            stdout="",
            stderr="",
            return_value=None,
            error=None,
            vars={"x": "int", "answer": "str"},
        )
        assert result.vars == {"x": "int", "answer": "str"}

    def test_execution_result_vars_defaults_none(self) -> None:
        """ExecutionResult.vars defaults to None."""
        result = ExecutionResult(
            status="ok",
            stdout="",
            stderr="",
            return_value=None,
            error=None,
        )
        assert result.vars is None


class TestResetNamespace:
    """Tests for namespace reset in executor."""

    def test_reset_namespace_sends_reset_action(self):
        """reset_namespace() sends {"action": "reset"} to container."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()

        with patch.object(executor, "_send_command", return_value={"status": "ok"}) as mock_cmd:
            executor.reset_namespace()

        mock_cmd.assert_called_once_with({"action": "reset"})

    def test_reset_namespace_returns_response(self):
        """reset_namespace() returns the response from the container."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()

        with patch.object(executor, "_send_command", return_value={"status": "ok"}):
            result = executor.reset_namespace()

        assert result == {"status": "ok"}
