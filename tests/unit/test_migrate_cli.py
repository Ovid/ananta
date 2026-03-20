"""Tests for python -m ananta.migrate CLI."""

from pathlib import Path
from unittest.mock import patch

from ananta.migrate import find_legacy_directories, perform_migration


def test_finds_existing_legacy_dirs(tmp_path: Path) -> None:
    """find_legacy_directories returns only dirs that exist without new counterpart."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    new = tmp_path / "ananta_data"

    pairs = [(legacy, new)]
    found = find_legacy_directories(pairs)

    assert len(found) == 1
    assert found[0] == (legacy, new)


def test_skips_missing_legacy_dirs(tmp_path: Path) -> None:
    """find_legacy_directories skips dirs that don't exist."""
    legacy = tmp_path / "shesha_data"
    new = tmp_path / "ananta_data"

    pairs = [(legacy, new)]
    found = find_legacy_directories(pairs)

    assert found == []


def test_skips_already_migrated(tmp_path: Path) -> None:
    """find_legacy_directories skips when new dir already exists."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    new = tmp_path / "ananta_data"
    new.mkdir()

    pairs = [(legacy, new)]
    found = find_legacy_directories(pairs)

    assert found == []


def test_perform_migration_renames_dirs(tmp_path: Path) -> None:
    """perform_migration renames legacy dirs to new paths."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    (legacy / "project1").mkdir()
    new = tmp_path / "ananta_data"

    perform_migration([(legacy, new)])

    assert not legacy.exists()
    assert new.exists()
    assert (new / "project1").exists()


def test_perform_migration_creates_parent_dirs(tmp_path: Path) -> None:
    """perform_migration creates parent directories if needed."""
    legacy = tmp_path / ".shesha" / "code-explorer"
    legacy.mkdir(parents=True)
    new = tmp_path / ".ananta" / "code-explorer"

    perform_migration([(legacy, new)])

    assert not legacy.exists()
    assert new.exists()
    assert new.parent.name == ".ananta"


def test_main_nothing_to_migrate(tmp_path: Path, capsys: object) -> None:
    """Main prints 'nothing to migrate' when no legacy dirs found."""
    with patch(
        "ananta.migrate.get_migration_pairs", return_value=[(tmp_path / "nope", tmp_path / "new")]
    ):
        from ananta.migrate import main

        main()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    assert "nothing to migrate" in captured.out.lower() or "all set" in captured.out.lower()
