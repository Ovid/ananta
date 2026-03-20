import logging
from pathlib import Path

import pytest

from ananta.migration import check_legacy_directory


def test_warns_when_legacy_dir_exists(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Migration check warns when old shesha directory exists."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    new = tmp_path / "ananta_data"

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, "shesha_data", "ananta_data")

    assert "shesha_data" in caplog.text
    assert "ananta_data" in caplog.text
    assert "rename" in caplog.text.lower() or "mv" in caplog.text.lower()


def test_silent_when_no_legacy_dir(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Migration check is silent when no legacy directory exists."""
    legacy = tmp_path / "shesha_data"
    new = tmp_path / "ananta_data"

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, "shesha_data", "ananta_data")

    assert caplog.text == ""


def test_silent_when_new_dir_already_exists(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Migration check is silent when user has already migrated."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    new = tmp_path / "ananta_data"
    new.mkdir()

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, "shesha_data", "ananta_data")

    assert caplog.text == ""


def test_mv_target_uses_new_path_not_legacy_parent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Migration message shows correct target for nested directories."""
    legacy = tmp_path / ".shesha" / "code-explorer"
    legacy.mkdir(parents=True)
    new = tmp_path / ".ananta" / "code-explorer"

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, ".shesha/code-explorer", ".ananta/code-explorer")

    # Target must be the new_path, not legacy_path.parent / new_name
    assert str(new) in caplog.text
