#!/usr/bin/env python3
"""Sandbox runner - executes Python code in isolation."""

import json
import struct
import sys
import traceback
from io import StringIO
from typing import Any

BinaryStream = Any  # Type alias for binary I/O streams


def _read_exactly(stream: BinaryStream, n: int) -> bytes:
    """Read exactly n bytes from binary stream. Raises ConnectionError on EOF."""
    data = b""
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed before message complete")
        data += chunk
    return data


def _read_message(stream: BinaryStream) -> dict[str, Any]:
    """Read a length-prefixed JSON message from binary stream."""
    raw_len = _read_exactly(stream, 4)
    length = struct.unpack(">I", raw_len)[0]
    payload = _read_exactly(stream, length)
    result: dict[str, Any] = json.loads(payload.decode("utf-8"))
    return result


def _write_message(stream: BinaryStream, data: dict[str, Any]) -> None:
    """Write a length-prefixed JSON message to binary stream."""
    payload = json.dumps(data).encode("utf-8")
    stream.write(struct.pack(">I", len(payload)) + payload)
    stream.flush()


# Global namespace for code execution (persists across executions)
NAMESPACE: dict[str, Any] = {}

BUILTINS_SET: frozenset[str] = frozenset(
    [
        "llm_query",
        "llm_query_batched",
        "FINAL",
        "FINAL_VAR",
        "FinalAnswer",
        "FinalVar",
        "SHOW_VARS",
        "context",
    ]
)


def show_vars() -> str:
    """List all non-private variables in the REPL namespace."""
    available = {
        k: type(v).__name__
        for k, v in NAMESPACE.items()
        if not k.startswith("_") and k not in BUILTINS_SET
    }
    if not available:
        return "No variables created yet. Use ```repl``` blocks to create variables."
    return f"Available variables: {available}"


def _list_vars() -> dict[str, str]:
    """List non-private, non-builtin variables and their types."""
    return {
        k: type(v).__name__
        for k, v in NAMESPACE.items()
        if not k.startswith("_") and k not in BUILTINS_SET
    }


def execute_code(code: str) -> dict[str, Any]:
    """Execute Python code and return results."""
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    return_value = None
    error = None

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        # Execute the code
        exec(code, NAMESPACE)

        # Check for special return values
        if "_return_value_" in NAMESPACE:
            return_value = NAMESPACE.pop("_return_value_")

    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {
        "status": "error" if error else "ok",
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue(),
        "return_value": return_value,
        "error": error,
        "vars": _list_vars(),
    }


def handle_llm_query(instruction: str, content: str = "") -> dict[str, Any]:
    """Request an LLM query from the host."""
    return {
        "action": "llm_query",
        "instruction": instruction,
        "content": content,
    }


def handle_llm_query_batch(prompts: list[str]) -> dict[str, Any]:
    """Request a batched LLM query from the host."""
    return {
        "action": "llm_query_batch",
        "prompts": prompts,
    }


def main() -> None:
    """Main loop: read JSON commands, execute, write JSON responses."""

    # Capture real binary stdout/stdin before any redirection happens during exec
    real_stdout_buf = sys.stdout.buffer
    real_stdin_buf = sys.stdin.buffer

    # Define FINAL and FINAL_VAR
    class FinalAnswer:
        def __init__(self, answer: str):
            self.answer = answer

    class FinalVar:
        def __init__(self, var_name: str):
            self.var_name = var_name

    def llm_query(instruction: str, content: str = "") -> str:
        """Request LLM query from host - blocks until response."""
        request = handle_llm_query(instruction, content)
        _write_message(real_stdout_buf, request)
        response = _read_message(real_stdin_buf)
        if response.get("action") == "llm_response":
            if "error" in response:
                raise ValueError(str(response["error"]))
            return str(response["result"])
        raise RuntimeError(f"Unexpected response: {response}")

    def llm_query_batched(prompts: list[str]) -> list[str]:
        """Request batched LLM queries from host - blocks until all complete."""
        request = handle_llm_query_batch(prompts)
        _write_message(real_stdout_buf, request)
        response = _read_message(real_stdin_buf)
        if response.get("action") == "llm_batch_response":
            if "error" in response:
                raise ValueError(str(response["error"]))
            return [str(r) for r in response["results"]]
        raise RuntimeError(f"Unexpected response: {response}")

    def make_final(answer: str) -> FinalAnswer:
        """Create FinalAnswer and register it for detection."""
        fa = FinalAnswer(answer)
        NAMESPACE["_return_value_"] = fa
        return fa

    def make_final_var(var_name: str) -> FinalVar:
        """Create FinalVar and register it for detection."""
        fv = FinalVar(var_name)
        NAMESPACE["_return_value_"] = fv
        return fv

    def register_builtins() -> None:
        """Register built-in functions in the namespace."""
        NAMESPACE["llm_query"] = llm_query
        NAMESPACE["llm_query_batched"] = llm_query_batched
        NAMESPACE["FINAL"] = make_final
        NAMESPACE["FINAL_VAR"] = make_final_var
        NAMESPACE["FinalAnswer"] = FinalAnswer
        NAMESPACE["FinalVar"] = FinalVar
        NAMESPACE["SHOW_VARS"] = show_vars

    register_builtins()

    while True:
        try:
            command = _read_message(real_stdin_buf)
        except (ConnectionError, json.JSONDecodeError):
            # ConnectionError: host closed the connection (normal shutdown).
            # JSONDecodeError: corrupted protocol stream (fail-closed).
            break
        try:
            action = command.get("action")

            if action == "execute":
                result = execute_code(command["code"])
                # Check if return_value is a FinalAnswer or FinalVar
                rv = result.get("return_value")
                if isinstance(rv, FinalAnswer):
                    result["final_answer"] = rv.answer
                    result["return_value"] = None  # Not JSON serializable
                elif isinstance(rv, FinalVar):
                    result["final_var"] = rv.var_name
                    result["final_value"] = (
                        str(NAMESPACE[rv.var_name]) if rv.var_name in NAMESPACE else None
                    )
                    result["return_value"] = None  # Not JSON serializable
                _write_message(real_stdout_buf, result)

            elif action == "setup":
                # Initialize context variable
                NAMESPACE["context"] = command.get("context", [])
                _write_message(real_stdout_buf, {"status": "ok"})

            elif action == "reset":
                NAMESPACE.clear()
                register_builtins()
                _write_message(real_stdout_buf, {"status": "ok"})

            elif action == "ping":
                _write_message(real_stdout_buf, {"status": "ok", "message": "pong"})

            else:
                err = {"status": "error", "error": f"Unknown action: {action}"}
                _write_message(real_stdout_buf, err)

        except Exception as e:
            _write_message(real_stdout_buf, {"status": "error", "error": str(e)})


if __name__ == "__main__":
    main()
