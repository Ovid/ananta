"""Tests for sandbox runner."""

import io
import json
import struct

from ananta.sandbox.runner import BUILTINS_SET, NAMESPACE, execute_code


def frame_message(data: dict) -> bytes:
    """Create a length-prefixed message frame for testing."""
    payload = json.dumps(data).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


def parse_messages(data: bytes) -> list[dict]:
    """Parse all length-prefixed messages from binary data."""
    stream = io.BytesIO(data)
    messages = []
    while True:
        header = stream.read(4)
        if len(header) < 4:
            break
        length = struct.unpack(">I", header)[0]
        payload = stream.read(length)
        if len(payload) < length:
            break
        messages.append(json.loads(payload.decode("utf-8")))
    return messages


class _MockStdio:
    """Mock stdio with .buffer attribute for binary protocol testing."""

    def __init__(self, buffer: io.BytesIO) -> None:
        self.buffer = buffer


class TestExecuteCode:
    """Tests for execute_code function."""

    def setup_method(self) -> None:
        """Clear namespace before each test."""
        NAMESPACE.clear()

    def test_execute_code_runs_python(self) -> None:
        """execute_code runs Python code and captures stdout."""
        result = execute_code("print('hello')")
        assert result["status"] == "ok"
        assert result["stdout"] == "hello\n"

    def test_execute_code_persists_namespace(self) -> None:
        """Variables set in one execute_code call persist to the next."""
        execute_code("x = 42")
        result = execute_code("print(x)")
        assert result["stdout"] == "42\n"


class TestResetAction:
    """Tests for the reset action in the runner main loop."""

    def test_reset_action_returns_ok(self) -> None:
        """Sending reset action returns {"status": "ok"}."""
        import sys

        from ananta.sandbox.runner import main

        stdin_buf = io.BytesIO(frame_message({"action": "reset"}))
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[0]["status"] == "ok"

    def test_reset_clears_user_vars_but_keeps_builtins(self) -> None:
        """Reset clears user-defined vars but preserves FINAL/llm_query."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message({"action": "execute", "code": "user_var = 'secret'"}),
                frame_message({"action": "reset"}),
                frame_message({"action": "execute", "code": "print('user_var' in dir())"}),
                frame_message({"action": "execute", "code": "print(callable(FINAL))"}),
                frame_message({"action": "execute", "code": "print(callable(llm_query))"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        # msg 0: execute result (setting user_var)
        # msg 1: reset result
        # msg 2: execute result (checking user_var gone)
        # msg 3: execute result (checking FINAL exists)
        # msg 4: execute result (checking llm_query exists)

        assert messages[2]["stdout"] == "False\n", "user_var should be cleared"
        assert messages[3]["stdout"] == "True\n", "FINAL should still exist"
        assert messages[4]["stdout"] == "True\n", "llm_query should still exist"


class TestRunnerInvalidJson:
    """Tests for runner handling of invalid JSON input."""

    def test_runner_exits_on_invalid_json(self) -> None:
        """Runner breaks out of main loop on JSONDecodeError (fail-closed)."""
        import sys

        from ananta.sandbox.runner import main

        # First message is valid, second has a valid length prefix but invalid JSON payload
        valid_msg = frame_message({"action": "ping"})
        invalid_payload = b"this is not valid json"
        invalid_msg = struct.pack(">I", len(invalid_payload)) + invalid_payload
        # Third message should NOT be processed
        third_msg = frame_message({"action": "ping"})

        stdin_buf = io.BytesIO(valid_msg + invalid_msg + third_msg)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        # First ping should succeed
        assert messages[0]["status"] == "ok"
        # Runner should have stopped after invalid JSON — no third ping response
        assert len(messages) == 1, (
            f"Expected only 1 response (runner should exit on invalid JSON), "
            f"got {len(messages)}: {messages}"
        )


class TestLlmQueryErrorHandling:
    """Tests for llm_query() error response handling."""

    def test_llm_query_raises_on_error_response(self) -> None:
        """llm_query() raises ValueError when host sends error field."""
        import sys

        from ananta.sandbox.runner import main

        error_msg = "Content size (735,490 chars) exceeds the sub-LLM limit"

        # The runner reads messages from stdin.buffer in sequence:
        # 1. {"action": "execute", "code": "result = llm_query('x', 'y')"}
        # 2. (llm_query writes request to stdout.buffer, then reads from stdin.buffer)
        # 3. {"action": "llm_response", "error": "Content size..."}
        # 4. (code raises ValueError, execute_code returns error result)

        stdin_data = b"".join(
            [
                frame_message(
                    {"action": "execute", "code": "result = llm_query('summarize', 'big')"}
                ),
                frame_message({"action": "llm_response", "error": error_msg}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        # First message: the llm_query request from the sandbox
        assert messages[0]["action"] == "llm_query"
        # Second message: the execute result (should be error from ValueError)
        assert messages[1]["status"] == "error"
        assert "ValueError" in messages[1]["error"]
        assert error_msg in messages[1]["error"]

    def test_llm_query_succeeds_on_normal_response(self) -> None:
        """llm_query() returns result string when response has no error field."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "result = llm_query('summarize', 'content')\nprint(result)",
                    }
                ),
                frame_message({"action": "llm_response", "result": "Analysis complete"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        # First message: the llm_query request
        assert messages[0]["action"] == "llm_query"
        # Second message: the execute result (should be ok)
        assert messages[1]["status"] == "ok"
        assert "Analysis complete" in messages[1]["stdout"]


class TestLlmQueryOptionalContent:
    """Tests for llm_query() with optional content argument."""

    def test_llm_query_single_arg_sends_empty_content(self) -> None:
        """llm_query('prompt') sends empty string as content field."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "result = llm_query('What is the answer?')\nprint(result)",
                    }
                ),
                frame_message({"action": "llm_response", "result": "42"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[0]["action"] == "llm_query"
        assert messages[0]["instruction"] == "What is the answer?"
        assert messages[0]["content"] == ""

        assert messages[1]["status"] == "ok"
        assert "42" in messages[1]["stdout"]

    def test_llm_query_two_args_still_works(self) -> None:
        """llm_query('instruction', 'content') still sends both fields."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "result = llm_query('classify', 'some data')\nprint(result)",
                    }
                ),
                frame_message({"action": "llm_response", "result": "done"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[0]["action"] == "llm_query"
        assert messages[0]["instruction"] == "classify"
        assert messages[0]["content"] == "some data"


class TestLlmQueryBatched:
    """Tests for llm_query_batched() function."""

    def test_llm_query_batched_sends_batch_request(self) -> None:
        """llm_query_batched sends a batch action with all prompts."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": (
                            "results = llm_query_batched("
                            "['classify: cat', 'classify: dog', 'classify: bird'])\n"
                            "print(results)"
                        ),
                    }
                ),
                frame_message({"action": "llm_batch_response", "results": ["cat", "dog", "bird"]}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[0]["action"] == "llm_query_batch"
        assert messages[0]["prompts"] == ["classify: cat", "classify: dog", "classify: bird"]

        assert messages[1]["status"] == "ok"
        assert "cat" in messages[1]["stdout"]
        assert "dog" in messages[1]["stdout"]
        assert "bird" in messages[1]["stdout"]

    def test_llm_query_batched_raises_on_error(self) -> None:
        """llm_query_batched raises ValueError when host sends error."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {"action": "execute", "code": "results = llm_query_batched(['prompt1'])"}
                ),
                frame_message({"action": "llm_batch_response", "error": "Batch failed"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[1]["status"] == "error"
        assert "ValueError" in messages[1]["error"]

    def test_llm_query_batched_preserves_order(self) -> None:
        """llm_query_batched returns results in same order as prompts."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": (
                            "results = llm_query_batched(['a', 'b', 'c'])\n"
                            "for i, r in enumerate(results):\n"
                            "    print(f'{i}:{r}')"
                        ),
                    }
                ),
                frame_message(
                    {"action": "llm_batch_response", "results": ["first", "second", "third"]}
                ),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[1]["status"] == "ok"
        assert "0:first" in messages[1]["stdout"]
        assert "1:second" in messages[1]["stdout"]
        assert "2:third" in messages[1]["stdout"]

    def test_llm_query_batched_available_after_reset(self) -> None:
        """llm_query_batched persists after namespace reset."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message({"action": "reset"}),
                frame_message({"action": "execute", "code": "print(callable(llm_query_batched))"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[1]["status"] == "ok"
        assert messages[1]["stdout"] == "True\n"


class TestFinalVarMissingVariable:
    """Tests for FINAL_VAR with missing sandbox variables."""

    def test_final_var_missing_variable_returns_none_not_empty(self) -> None:
        """FINAL_VAR for a missing variable must send None, not empty string."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "FINAL_VAR('nonexistent_var')",
                    }
                ),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        result = messages[0]
        assert result["final_var"] == "nonexistent_var"
        # Must be None so the engine can detect missing variable and retry
        assert result["final_value"] is None

    def test_final_var_existing_variable_returns_value(self) -> None:
        """FINAL_VAR for an existing variable returns its string value."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "my_result = 'hello world'\nFINAL_VAR('my_result')",
                    }
                ),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        result = messages[0]
        assert result["final_var"] == "my_result"
        assert result["final_value"] == "hello world"

    def test_final_var_none_valued_variable_returns_none(self) -> None:
        """FINAL_VAR for a variable holding Python None must return None,
        not the string 'None'."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {
                        "action": "execute",
                        "code": "my_var = None\nFINAL_VAR('my_var')",
                    }
                ),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        result = messages[0]
        assert result["final_var"] == "my_var"
        # None-valued variable should be treated like missing, not "None" string
        assert result["final_value"] is None


class TestLengthPrefixHelpers:
    """Tests for length-prefix protocol helpers."""

    def test_read_message_reads_length_prefixed_json(self) -> None:
        """_read_message reads 4-byte BE length prefix then exact payload."""
        from ananta.sandbox.runner import _read_message

        data = {"action": "execute", "code": "print('hello')"}
        stream = io.BytesIO(frame_message(data))
        result = _read_message(stream)
        assert result == data

    def test_read_message_handles_large_payload(self) -> None:
        """_read_message handles payloads larger than typical buffers."""
        from ananta.sandbox.runner import _read_message

        data = {"action": "llm_response", "result": "x" * 100_000}
        stream = io.BytesIO(frame_message(data))
        result = _read_message(stream)
        assert result == data

    def test_write_message_writes_length_prefixed_json(self) -> None:
        """_write_message writes 4-byte BE length prefix + JSON payload."""
        from ananta.sandbox.runner import _write_message

        data = {"status": "ok", "stdout": "hello\n"}
        stream = io.BytesIO()
        _write_message(stream, data)
        written = stream.getvalue()

        # Verify length prefix
        length = struct.unpack(">I", written[:4])[0]
        payload = written[4:]
        assert len(payload) == length
        assert json.loads(payload.decode("utf-8")) == data

    def test_write_message_flushes_stream(self) -> None:
        """_write_message calls flush() on the stream."""
        from unittest.mock import MagicMock

        from ananta.sandbox.runner import _write_message

        mock_stream = MagicMock()
        _write_message(mock_stream, {"status": "ok"})
        mock_stream.flush.assert_called_once()

    def test_read_exactly_raises_on_eof(self) -> None:
        """_read_exactly raises ConnectionError on EOF mid-read."""
        from ananta.sandbox.runner import _read_exactly

        stream = io.BytesIO(b"abc")  # Only 3 bytes
        with __import__("pytest").raises(ConnectionError, match="Connection closed"):
            _read_exactly(stream, 10)  # Ask for 10

    def test_read_exactly_reads_exact_bytes(self) -> None:
        """_read_exactly reads exactly n bytes from stream."""
        from ananta.sandbox.runner import _read_exactly

        stream = io.BytesIO(b"hello world")
        result = _read_exactly(stream, 5)
        assert result == b"hello"

    def test_read_message_multiple_messages(self) -> None:
        """_read_message reads only one message, leaving rest in stream."""
        from ananta.sandbox.runner import _read_message

        msg1 = {"action": "ping"}
        msg2 = {"action": "reset"}
        stream = io.BytesIO(frame_message(msg1) + frame_message(msg2))

        result1 = _read_message(stream)
        assert result1 == msg1

        result2 = _read_message(stream)
        assert result2 == msg2


def test_partial_in_builtins_set():
    """PARTIAL and PartialAnswer must be in BUILTINS_SET so SHOW_VARS excludes them."""
    assert "PARTIAL" in BUILTINS_SET
    assert "PartialAnswer" in BUILTINS_SET


class TestPartialAnswer:
    """Tests for PARTIAL() callable in the sandbox protocol."""

    def test_partial_produces_partial_answer_in_result(self) -> None:
        """PARTIAL('text') in sandbox sets result['partial_answer']."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message(
                    {"action": "execute", "code": "PARTIAL('Found 7 titles but no dates')"}
                ),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        result = messages[0]
        assert result["partial_answer"] == "Found 7 titles but no dates"
        assert result["return_value"] is None

    def test_partial_callable_after_reset(self) -> None:
        """PARTIAL remains callable after namespace reset."""
        import sys

        from ananta.sandbox.runner import main

        stdin_data = b"".join(
            [
                frame_message({"action": "reset"}),
                frame_message({"action": "execute", "code": "print(callable(PARTIAL))"}),
            ]
        )
        stdin_buf = io.BytesIO(stdin_data)
        stdout_buf = io.BytesIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = _MockStdio(stdin_buf)
            sys.stdout = _MockStdio(stdout_buf)
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        messages = parse_messages(stdout_buf.getvalue())
        assert messages[1]["status"] == "ok"
        assert messages[1]["stdout"] == "True\n"
