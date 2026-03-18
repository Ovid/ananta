"""Tests for path traversal protection."""

from pathlib import Path

import pytest

from shesha.security.paths import PathTraversalError, safe_path


class TestSafePath:
    """Tests for safe_path function."""

    def test_simple_path_under_base(self, tmp_path: Path) -> None:
        """Simple path stays under base."""
        result = safe_path(tmp_path, "subdir", "file.txt")
        assert result == tmp_path / "subdir" / "file.txt"

    def test_traversal_with_dotdot_raises(self, tmp_path: Path) -> None:
        """Path with .. that escapes base raises error."""
        with pytest.raises(PathTraversalError):
            safe_path(tmp_path, "..", "escape.txt")

    def test_traversal_in_middle_raises(self, tmp_path: Path) -> None:
        """Path with .. in middle that escapes raises error."""
        with pytest.raises(PathTraversalError):
            safe_path(tmp_path, "subdir", "..", "..", "escape.txt")

    def test_dotdot_staying_in_base_ok(self, tmp_path: Path) -> None:
        """Path with .. that stays under base is allowed."""
        result = safe_path(tmp_path, "subdir", "..", "other.txt")
        assert result == tmp_path / "other.txt"

    def test_absolute_path_escape_raises(self, tmp_path: Path) -> None:
        """Absolute path component raises if it escapes."""
        with pytest.raises(PathTraversalError):
            safe_path(tmp_path, "/etc/passwd")
