"""Tests for multi_repo example script."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add examples to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples"))


def test_multi_repo_script_importable():
    """multi_repo.py can be imported."""
    import multi_repo

    assert hasattr(multi_repo, "main")


def test_multi_repo_has_parse_args():
    """multi_repo.py has argument parser."""
    import multi_repo

    assert hasattr(multi_repo, "parse_args")


class TestParseArgs:
    """Tests for parse_args function."""

    def test_repos_optional(self) -> None:
        """No args should work (for picker mode)."""
        from multi_repo import parse_args

        args = parse_args([])
        assert args.repos == []
        assert args.prd is None

    def test_repos_positional(self) -> None:
        """Repo URLs captured as positional args."""
        from multi_repo import parse_args

        args = parse_args(["https://github.com/org/a", "https://github.com/org/b"])
        assert args.repos == ["https://github.com/org/a", "https://github.com/org/b"]

    def test_prd_flag(self) -> None:
        """--prd flag captures file path."""
        from multi_repo import parse_args

        args = parse_args(["--prd", "spec.md"])
        assert args.prd == "spec.md"

    def test_prd_with_repos(self) -> None:
        """--prd works together with repos."""
        from multi_repo import parse_args

        args = parse_args(["repo1", "repo2", "--prd", "spec.md"])
        assert args.repos == ["repo1", "repo2"]
        assert args.prd == "spec.md"

    def test_verbose_flag(self) -> None:
        """--verbose flag should be captured."""
        from multi_repo import parse_args

        args = parse_args(["--verbose"])
        assert args.verbose


class TestReadPrd:
    """Tests for PRD reading logic."""

    def test_read_prd_from_file(self, tmp_path: Path) -> None:
        """--prd reads content from file."""
        from multi_repo import read_prd

        prd_file = tmp_path / "spec.md"
        prd_file.write_text("# Requirements\n\nDo the thing.")
        result = read_prd(str(prd_file))
        assert result == "# Requirements\n\nDo the thing."

    def test_read_prd_file_not_found(self) -> None:
        """--prd with non-existent file raises SystemExit."""
        from multi_repo import read_prd

        with pytest.raises(SystemExit):
            read_prd("/nonexistent/path.md")

    def test_read_prd_none_falls_back_to_stdin(self) -> None:
        """No --prd prompts for stdin input."""
        from multi_repo import read_prd

        with patch("multi_repo.read_multiline_input", return_value="PRD from stdin"):
            result = read_prd(None)
        assert result == "PRD from stdin"


class TestCollectReposFromStorages:
    """Tests for collect_repos_from_storages."""

    def test_returns_repos_from_both_storages(self) -> None:
        """Repos from both storages are returned."""
        from multi_repo import collect_repos_from_storages

        mock_multi = MagicMock()
        mock_multi.list_projects.return_value = ["org-auth"]
        mock_multi.get_project_info.return_value = MagicMock(
            project_id="org-auth",
            source_url="https://github.com/org/auth",
            is_local=False,
            source_exists=True,
        )

        mock_explorer = MagicMock()
        mock_explorer.list_projects.return_value = ["org-api"]
        mock_explorer.get_project_info.return_value = MagicMock(
            project_id="org-api",
            source_url="https://github.com/org/api",
            is_local=False,
            source_exists=True,
        )

        repos = collect_repos_from_storages(mock_multi, mock_explorer)
        assert len(repos) == 2
        ids = [r[0] for r in repos]
        assert "org-auth" in ids
        assert "org-api" in ids

    def test_deduplicates_preferring_multi_repo(self) -> None:
        """Same project_id in both storages uses multi-repo copy."""
        from multi_repo import collect_repos_from_storages

        mock_multi = MagicMock()
        mock_multi.list_projects.return_value = ["org-repo"]
        mock_multi.get_project_info.return_value = MagicMock(
            project_id="org-repo",
            source_url="https://github.com/org/repo",
            is_local=False,
            source_exists=True,
        )

        mock_explorer = MagicMock()
        mock_explorer.list_projects.return_value = ["org-repo"]
        mock_explorer.get_project_info.return_value = MagicMock(
            project_id="org-repo",
            source_url="https://github.com/org/repo",
            is_local=False,
            source_exists=True,
        )

        repos = collect_repos_from_storages(mock_multi, mock_explorer)
        assert len(repos) == 1
        assert repos[0][2] == "multi-repo"

    def test_empty_storages(self) -> None:
        """No repos in either storage returns empty list."""
        from multi_repo import collect_repos_from_storages

        mock_multi = MagicMock()
        mock_multi.list_projects.return_value = []

        mock_explorer = MagicMock()
        mock_explorer.list_projects.return_value = []

        repos = collect_repos_from_storages(mock_multi, mock_explorer)
        assert repos == []

    def test_explorer_only(self) -> None:
        """Repos only in explorer storage are returned."""
        from multi_repo import collect_repos_from_storages

        mock_multi = MagicMock()
        mock_multi.list_projects.return_value = []

        mock_explorer = MagicMock()
        mock_explorer.list_projects.return_value = ["Ovid-ananta"]
        mock_explorer.get_project_info.return_value = MagicMock(
            project_id="Ovid-ananta",
            source_url="https://github.com/Ovid/ananta/",
            is_local=False,
            source_exists=True,
        )

        repos = collect_repos_from_storages(mock_multi, mock_explorer)
        assert len(repos) == 1
        assert repos[0][0] == "Ovid-ananta"
        assert repos[0][2] == "repo-explorer"


class TestShowMultiPicker:
    """Tests for show_multi_picker."""

    def test_all_selected_by_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        """All repos start selected; 'done' returns all."""
        from multi_repo import show_multi_picker

        repos = [
            ("org-auth", "https://github.com/org/auth", "multi-repo"),
            ("org-api", "https://github.com/org/api", "repo-explorer"),
        ]

        with patch("builtins.input", return_value="done"):
            result = show_multi_picker(repos)

        assert len(result) == 2
        assert ("org-auth", "https://github.com/org/auth", "multi-repo") in result
        assert ("org-api", "https://github.com/org/api", "repo-explorer") in result

    def test_toggle_deselects(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Entering a number deselects that repo."""
        from multi_repo import show_multi_picker

        repos = [
            ("org-auth", "https://github.com/org/auth", "multi-repo"),
            ("org-api", "https://github.com/org/api", "repo-explorer"),
        ]

        with patch("builtins.input", side_effect=["2", "done"]):
            result = show_multi_picker(repos)

        assert len(result) == 1
        assert result[0][0] == "org-auth"

    def test_toggle_reselects(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Entering same number twice re-selects."""
        from multi_repo import show_multi_picker

        repos = [
            ("org-auth", "https://github.com/org/auth", "multi-repo"),
            ("org-api", "https://github.com/org/api", "repo-explorer"),
        ]

        with patch("builtins.input", side_effect=["2", "2", "done"]):
            result = show_multi_picker(repos)

        assert len(result) == 2

    def test_add_url(self, capsys: pytest.CaptureFixture[str]) -> None:
        """'a' prompts for URL and adds it."""
        from multi_repo import show_multi_picker

        repos = [("org-auth", "https://github.com/org/auth", "multi-repo")]

        with patch("builtins.input", side_effect=["a", "https://github.com/org/new", "done"]):
            result = show_multi_picker(repos)

        assert len(result) == 2
        added = [r for r in result if r[0] == "https://github.com/org/new"]
        assert len(added) == 1

    def test_deselect_all_shows_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Deselecting all repos and hitting 'done' shows error and re-prompts."""
        from multi_repo import show_multi_picker

        repos = [("org-auth", "https://github.com/org/auth", "multi-repo")]

        with patch("builtins.input", side_effect=["1", "done", "1", "done"]):
            result = show_multi_picker(repos)

        captured = capsys.readouterr()
        assert "At least one repo must be selected" in captured.out
        assert len(result) == 1

    def test_displays_grouped_by_storage(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Repos are displayed grouped by storage label."""
        from multi_repo import show_multi_picker

        repos = [
            ("org-auth", "https://github.com/org/auth", "multi-repo"),
            ("org-api", "https://github.com/org/api", "repo-explorer"),
        ]

        with patch("builtins.input", return_value="done"):
            show_multi_picker(repos)

        captured = capsys.readouterr()
        assert "[multi-repo]" in captured.out
        assert "[repo-explorer]" in captured.out


class TestMainIntegration:
    """Tests for main() wiring."""

    def test_no_args_shows_picker(self) -> None:
        """No CLI args triggers picker."""
        import os
        import sys as sys_mod

        from multi_repo import main

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["org-auth"]
        mock_ananta.get_project_info.return_value = MagicMock(
            project_id="org-auth",
            source_url="https://github.com/org/auth",
            is_local=False,
            source_exists=True,
        )

        picker_result = [
            ("org-auth", "https://github.com/org/auth", "multi-repo"),
        ]
        with patch.object(sys_mod, "argv", ["multi_repo.py"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("multi_repo.Ananta", return_value=mock_ananta):
                    with patch("multi_repo.AnantaConfig"):
                        with patch(
                            "multi_repo.show_multi_picker",
                            return_value=picker_result,
                        ) as mock_picker:
                            with patch(
                                "multi_repo.collect_repos_from_storages",
                                return_value=picker_result,
                            ):
                                with patch("multi_repo.MultiRepoAnalyzer") as mock_analyzer_cls:
                                    mock_analyzer = MagicMock()
                                    mock_analyzer.repos = ["org-auth"]
                                    mock_analyzer.failed_repos = {}
                                    mock_analyzer_cls.return_value = mock_analyzer
                                    with patch("multi_repo.read_prd", return_value="some prd"):
                                        with patch("builtins.input", return_value="n"):
                                            try:
                                                main()
                                            except (SystemExit, Exception):
                                                pass  # may exit; we check mock below

        mock_picker.assert_called_once()

    def test_repos_args_skips_picker(self) -> None:
        """CLI repo args skip the picker."""
        import os
        import sys as sys_mod

        from multi_repo import main

        mock_ananta = MagicMock()

        with patch.object(sys_mod, "argv", ["multi_repo.py", "https://github.com/org/auth"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("multi_repo.Ananta", return_value=mock_ananta):
                    with patch("multi_repo.AnantaConfig"):
                        with patch("multi_repo.show_multi_picker") as mock_picker:
                            with patch("multi_repo.MultiRepoAnalyzer") as mock_analyzer_cls:
                                mock_analyzer = MagicMock()
                                mock_analyzer.repos = ["org-auth"]
                                mock_analyzer.failed_repos = {}
                                mock_analyzer_cls.return_value = mock_analyzer
                                with patch("multi_repo.read_prd", return_value="some prd"):
                                    with patch("builtins.input", return_value="n"):
                                        try:
                                            main()
                                        except (SystemExit, Exception):
                                            pass  # may exit; we check mock below

        mock_picker.assert_not_called()

    def test_no_api_key_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing API key should print error and exit."""
        import os
        import sys as sys_mod

        from multi_repo import main

        with patch.object(sys_mod, "argv", ["multi_repo.py"]):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "ANANTA_API_KEY" in captured.out
