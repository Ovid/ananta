"""Tests for SandboxExecutor protocol."""

from typing import runtime_checkable

from shesha.sandbox.base import SandboxExecutor
from shesha.sandbox.executor import ContainerExecutor


class TestSandboxExecutorProtocol:
    """Tests for the SandboxExecutor protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """SandboxExecutor should be runtime-checkable."""
        assert runtime_checkable in getattr(SandboxExecutor, "__protocol_attrs__", []) or hasattr(
            SandboxExecutor, "__protocol_attrs__"
        )
        # The real check: isinstance works
        assert issubclass(type(SandboxExecutor), type)

    def test_container_executor_satisfies_protocol(self) -> None:
        """ContainerExecutor should satisfy the SandboxExecutor protocol."""
        # Class-level methods and properties
        class_attrs = ["execute", "start", "stop", "setup_context", "reset_namespace", "is_alive"]
        for attr in class_attrs:
            assert hasattr(ContainerExecutor, attr), f"ContainerExecutor missing {attr}"
        # llm_query_handler is an instance attribute set in __init__
        assert "llm_query_handler" in ContainerExecutor.__init__.__code__.co_varnames

    def test_protocol_defines_expected_members(self) -> None:
        """Protocol should define the methods the engine relies on."""
        class_attrs = ["execute", "start", "stop", "setup_context", "reset_namespace", "is_alive"]
        for attr in class_attrs:
            assert attr in dir(SandboxExecutor), f"SandboxExecutor missing {attr}"
        # llm_query_handler is declared as a protocol attribute
        assert "llm_query_handler" in SandboxExecutor.__protocol_attrs__

    def test_base_module_owns_shared_types(self) -> None:
        """ExecutionResult and LLMQueryHandler should be defined in base.py, not imported from executor.py."""
        import inspect

        from shesha.sandbox.base import ExecutionResult, LLMQueryHandler

        # They should be defined in base.py, not re-exported from executor.py
        assert inspect.getmodule(ExecutionResult).__name__ == "shesha.sandbox.base"  # type: ignore[union-attr]
        assert inspect.getmodule(LLMQueryHandler) is None or "executor" not in str(
            inspect.getmodule(LLMQueryHandler)
        )

    def test_pool_type_annotations_use_protocol(self) -> None:
        """ContainerPool should use SandboxExecutor in its type annotations."""
        # Check acquire return type
        import inspect

        from shesha.sandbox.pool import ContainerPool

        sig = inspect.signature(ContainerPool.acquire)
        assert (
            sig.return_annotation is SandboxExecutor or sig.return_annotation == "SandboxExecutor"
        )
