"""Protocol for sandbox executors."""

from typing import Any, Protocol, runtime_checkable

from shesha.sandbox.executor import ExecutionResult, LLMQueryHandler


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
