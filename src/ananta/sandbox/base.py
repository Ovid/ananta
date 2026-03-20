"""Protocol and shared types for sandbox executors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ExecutionResult:
    """Result of code execution in sandbox."""

    status: str
    stdout: str
    stderr: str
    return_value: Any
    error: str | None
    final_answer: str | None = None
    final_var: str | None = None
    final_value: str | None = None
    partial_answer: str | None = None
    vars: dict[str, str] | None = None


LLMQueryHandler = Callable[[str, str], str]  # (instruction, content) -> response


@runtime_checkable
class SandboxExecutor(Protocol):
    """Protocol for sandbox executors.

    Defines the interface that RLMEngine and ContainerPool depend on,
    enabling substitution of mock executors for testing or non-Docker backends.
    """

    llm_query_handler: LLMQueryHandler | None

    @property
    def is_alive(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def setup_context(self, context: list[str]) -> None: ...

    def reset_namespace(self) -> dict[str, Any]: ...

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult: ...
