"""Tests for SHOW_VARS sandbox function."""

from ananta.sandbox.runner import NAMESPACE, execute_code


class TestShowVars:
    """Tests for show_vars function."""

    def setup_method(self) -> None:
        """Clear namespace before each test."""
        NAMESPACE.clear()

    def test_show_vars_returns_user_variables(self) -> None:
        """SHOW_VARS returns user-created variables, not builtins."""
        from ananta.sandbox.runner import show_vars

        # Simulate builtins
        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        # Create user variable via execute_code
        execute_code("my_var = 42")

        result = show_vars()
        assert "my_var" in result
        assert "llm_query" not in result
        assert "FINAL" not in result
        assert "SHOW_VARS" not in result
        assert "context" not in result

    def test_show_vars_empty_namespace(self) -> None:
        """SHOW_VARS returns helpful message when no user vars exist."""
        from ananta.sandbox.runner import show_vars

        # Only builtins
        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        result = show_vars()
        assert "No variables created yet" in result

    def test_show_vars_shows_types(self) -> None:
        """SHOW_VARS includes variable types."""
        from ananta.sandbox.runner import show_vars

        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        execute_code("x = 42\ny = 'hello'")

        result = show_vars()
        assert "int" in result
        assert "str" in result

    def test_show_vars_excludes_private_vars(self) -> None:
        """SHOW_VARS excludes variables starting with underscore."""
        from ananta.sandbox.runner import show_vars

        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        execute_code("_private = 'hidden'\npublic = 'visible'")

        result = show_vars()
        assert "_private" not in result
        assert "public" in result

    def test_execute_code_returns_vars_field(self) -> None:
        """execute_code result includes vars dict of user variables."""
        NAMESPACE.clear()
        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = lambda: None
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        result = execute_code("x = 42\ny = 'hello'")
        assert "vars" in result
        assert "x" in result["vars"]
        assert result["vars"]["x"] == "int"
        assert "y" in result["vars"]
        assert result["vars"]["y"] == "str"
        # Builtins should not appear
        assert "llm_query" not in result["vars"]

    def test_execute_code_vars_empty_when_no_user_vars(self) -> None:
        """execute_code vars is empty dict when only builtins exist."""
        NAMESPACE.clear()
        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = lambda: None
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        result = execute_code("pass")
        assert result["vars"] == {}
