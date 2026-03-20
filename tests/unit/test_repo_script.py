"""Tests for repo.py script."""

from unittest.mock import MagicMock, patch

import pytest


class TestParseArgs:
    """Tests for parse_args function."""

    def test_no_args(self) -> None:
        """No args should work (for picker mode)."""
        from examples.repo import parse_args

        args = parse_args([])
        assert args.repo is None
        assert not args.update

    def test_no_verbose_flag(self) -> None:
        """--verbose flag should no longer exist."""
        from examples.repo import parse_args

        with pytest.raises(SystemExit):
            parse_args(["--verbose"])

    def test_repo_positional(self) -> None:
        """Repo URL should be captured as positional arg."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo"])
        assert args.repo == "https://github.com/user/repo"

    def test_local_path(self) -> None:
        """Local path should be captured."""
        from examples.repo import parse_args

        args = parse_args(["/path/to/repo"])
        assert args.repo == "/path/to/repo"

    def test_update_flag(self) -> None:
        """--update flag should be captured."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo", "--update"])
        assert args.update

    def test_pristine_flag_default_false(self) -> None:
        """--pristine flag defaults to False."""
        from examples.repo import parse_args

        args = parse_args([])
        assert not args.pristine

    def test_pristine_flag(self) -> None:
        """--pristine flag should be captured."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo", "--pristine"])
        assert args.pristine

    def test_verify_default_none(self) -> None:
        """--verify defaults to None so config file settings are preserved."""
        from examples.repo import parse_args

        args = parse_args([])
        assert args.verify is None

    def test_verify_flag(self) -> None:
        """--verify flag sets verify=True."""
        from examples.repo import parse_args

        args = parse_args(["https://github.com/user/repo", "--verify"])
        assert args.verify is True


class TestShowPicker:
    """Tests for show_picker function."""

    def test_no_projects_returns_none(self) -> None:
        """No projects should prompt for URL, not show picker."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = []

        # Should return None when no projects (prompt_for_repo handles that case)
        result = show_picker(mock_ananta)
        assert result is None

    def test_with_projects_shows_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Projects should be listed with numbers."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a", "project-b"]

        with patch("builtins.input", return_value="1"):
            value, is_existing = show_picker(mock_ananta)

        captured = capsys.readouterr()
        assert "1. project-a" in captured.out
        assert "2. project-b" in captured.out
        assert value == "project-a"
        assert is_existing is True

    def test_select_by_number(self) -> None:
        """Selecting a number returns corresponding project name with is_existing=True."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a", "project-b"]

        with patch("builtins.input", return_value="2"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "project-b"
        assert is_existing is True

    def test_enter_new_url(self) -> None:
        """Entering a URL should return it with is_existing=False."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="https://github.com/new/repo"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "https://github.com/new/repo"
        assert is_existing is False

    def test_exit_command_returns_empty(self) -> None:
        """Typing 'exit' should return empty string to trigger exit."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="exit"):
            value, is_existing = show_picker(mock_ananta)

        assert value == ""
        assert is_existing is False

    def test_quit_command_returns_empty(self) -> None:
        """Typing 'quit' should return empty string to trigger exit."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="quit"):
            value, is_existing = show_picker(mock_ananta)

        assert value == ""
        assert is_existing is False

    def test_invalid_input_reprompts(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid input like 'asdf' should show error and reprompt."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        # First input is invalid, second is valid exit
        inputs = iter(["asdf", "exit"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            value, is_existing = show_picker(mock_ananta)

        captured = capsys.readouterr()
        assert "Invalid input" in captured.out
        assert value == ""  # Exited on second input

    def test_accepts_https_url(self) -> None:
        """HTTPS URLs should be accepted."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="https://github.com/org/repo"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "https://github.com/org/repo"
        assert is_existing is False

    def test_accepts_ssh_url(self) -> None:
        """SSH URLs should be accepted."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="git@github.com:org/repo.git"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "git@github.com:org/repo.git"
        assert is_existing is False

    def test_accepts_absolute_path(self) -> None:
        """Absolute paths should be accepted."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="/path/to/repo"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "/path/to/repo"
        assert is_existing is False

    def test_accepts_home_path(self) -> None:
        """Paths starting with ~ should be accepted."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="~/projects/repo"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "~/projects/repo"
        assert is_existing is False

    def test_accepts_relative_path(self) -> None:
        """Paths starting with ./ or ../ should be accepted."""
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["project-a"]

        with patch("builtins.input", return_value="./local-repo"):
            value, is_existing = show_picker(mock_ananta)

        assert value == "./local-repo"
        assert is_existing is False


class TestPromptForRepo:
    """Tests for prompt_for_repo function."""

    def test_returns_input(self) -> None:
        """Should return user input."""
        from examples.repo import prompt_for_repo

        with patch("builtins.input", return_value="https://github.com/user/repo"):
            result = prompt_for_repo()

        assert result == "https://github.com/user/repo"

    def test_strips_whitespace(self) -> None:
        """Should strip whitespace from input."""
        from examples.repo import prompt_for_repo

        with patch("builtins.input", return_value="  /path/to/repo  "):
            result = prompt_for_repo()

        assert result == "/path/to/repo"


class TestHandleUpdates:
    """Tests for handle_updates function."""

    def test_created_status_returns_same(self) -> None:
        """Status 'created' should return the same result."""
        from examples.repo import handle_updates

        mock_result = MagicMock()
        mock_result.status = "created"
        mock_result.files_ingested = 42

        result = handle_updates(mock_result, auto_update=False)
        assert result is mock_result

    def test_unchanged_status_returns_same(self) -> None:
        """Status 'unchanged' should return the same result."""
        from examples.repo import handle_updates

        mock_result = MagicMock()
        mock_result.status = "unchanged"

        result = handle_updates(mock_result, auto_update=False)
        assert result is mock_result

    def test_updates_available_auto_applies(self) -> None:
        """With --update flag, should auto-apply updates."""
        from examples.repo import handle_updates

        updated_result = MagicMock()
        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.apply_updates.return_value = updated_result

        result = handle_updates(mock_result, auto_update=True)
        mock_result.apply_updates.assert_called_once()
        assert result is updated_result

    def test_updates_available_prompts_user_yes(self) -> None:
        """Without --update, should prompt and apply if 'y'."""
        from examples.repo import handle_updates

        updated_result = MagicMock()
        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.project.project_id = "test-repo"
        mock_result.apply_updates.return_value = updated_result

        with patch("builtins.input", return_value="y"):
            result = handle_updates(mock_result, auto_update=False)

        mock_result.apply_updates.assert_called_once()
        assert result is updated_result

    def test_updates_available_prompts_user_no(self) -> None:
        """Without --update, should prompt and skip if 'n'."""
        from examples.repo import handle_updates

        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.project.project_id = "test-repo"

        with patch("builtins.input", return_value="n"):
            result = handle_updates(mock_result, auto_update=False)

        mock_result.apply_updates.assert_not_called()
        assert result is mock_result


class TestMain:
    """Tests for main function."""

    def test_docker_not_running_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Docker not running should print clean error and exit."""
        import os
        import sys

        from examples.repo import main

        with patch.object(sys, "argv", ["repo.py", "https://github.com/test/repo"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.AnantaConfig"):
                    with patch(
                        "examples.repo.Ananta",
                        side_effect=RuntimeError(
                            "Docker is not running. Please start Docker Desktop and try again."
                        ),
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Docker" in captured.out
        assert "not running" in captured.out
        # Should NOT have traceback
        assert "Traceback" not in captured.out

    def test_no_api_key_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing API key should print error and exit."""
        import os
        import sys

        from examples.repo import main

        # Mock sys.argv so parse_args doesn't see pytest's args
        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "ANANTA_API_KEY" in captured.out

    def test_picker_existing_project_launches_tui(self) -> None:
        """Selecting existing project via picker should launch TUI."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "unchanged"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "existing-project"

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["existing-project"]
        mock_ananta.check_repo_for_updates.return_value = mock_result
        mock_ananta.get_analysis.return_value = None

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with patch("examples.repo.AnantaTUI") as mock_tui_class:
                            mock_tui = MagicMock()
                            mock_tui_class.return_value = mock_tui
                            with patch("builtins.input", return_value="1"):
                                main()

        # Should check for updates when loading existing project
        mock_ananta.check_repo_for_updates.assert_called_once_with("existing-project")
        # Should create TUI and run it
        mock_tui_class.assert_called_once()
        mock_tui.run.assert_called_once()

    def test_picker_existing_project_with_update_flag_applies_updates(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Selecting existing project with --update should auto-apply updates."""
        import os
        import sys

        from examples.repo import main

        # First result has updates available
        mock_result = MagicMock()
        mock_result.status = "updates_available"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "existing-project"

        # After applying updates
        updated_result = MagicMock()
        updated_result.status = "created"
        updated_result.files_ingested = 15
        updated_result.project = mock_result.project
        mock_result.apply_updates.return_value = updated_result

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["existing-project"]
        mock_ananta.check_repo_for_updates.return_value = mock_result
        mock_ananta.get_analysis.return_value = None

        with patch.object(sys, "argv", ["repo.py", "--update"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with patch("examples.repo.AnantaTUI") as mock_tui_class:
                            mock_tui = MagicMock()
                            mock_tui_class.return_value = mock_tui
                            with patch("builtins.input", return_value="1"):
                                main()

        # Should apply updates when --update flag is set
        mock_result.apply_updates.assert_called_once()
        captured = capsys.readouterr()
        assert "Applying updates" in captured.out

    def test_picker_new_url_uses_create_project_from_repo(self) -> None:
        """Entering new URL via picker should use create_project_from_repo."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "created"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "new-repo"

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["existing-project"]
        mock_ananta.create_project_from_repo.return_value = mock_result
        mock_ananta.get_analysis.return_value = None

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with patch("examples.repo.AnantaTUI") as mock_tui_class:
                            mock_tui = MagicMock()
                            mock_tui_class.return_value = mock_tui
                            with patch(
                                "builtins.input",
                                return_value="https://github.com/new/repo",
                            ):
                                main()

        # Should use create_project_from_repo for new URL, NOT get_project
        mock_ananta.create_project_from_repo.assert_called_once_with("https://github.com/new/repo")
        mock_ananta.get_project.assert_not_called()

    def test_tui_created_with_analysis_context(self) -> None:
        """TUI should be created with analysis_context when analysis exists."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "unchanged"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "test-project"

        from ananta.models import RepoAnalysis

        mock_analysis = RepoAnalysis(
            version="1",
            generated_at="2026-02-06T10:30:00Z",
            head_sha="abc123",
            overview="Test overview",
            components=[],
            external_dependencies=[],
        )

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["test-project"]
        mock_ananta.check_repo_for_updates.return_value = mock_result
        mock_ananta.get_analysis.return_value = mock_analysis
        mock_ananta.get_analysis_status.return_value = "current"

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with patch("examples.repo.AnantaTUI") as mock_tui_class:
                            mock_tui = MagicMock()
                            mock_tui_class.return_value = mock_tui
                            with patch("builtins.input", return_value="1"):
                                main()

        # TUI should be created with analysis_context
        call_kwargs = mock_tui_class.call_args[1]
        assert call_kwargs["analysis_context"] is not None
        assert "Test overview" in call_kwargs["analysis_context"]

    def test_tui_created_without_analysis_context_when_pristine(self) -> None:
        """TUI should be created without analysis_context when --pristine is set."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "unchanged"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "test-project"

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["test-project"]
        mock_ananta.check_repo_for_updates.return_value = mock_result
        mock_ananta.get_analysis_status.return_value = "current"

        with patch.object(sys, "argv", ["repo.py", "--pristine"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with patch("examples.repo.AnantaTUI") as mock_tui_class:
                            mock_tui = MagicMock()
                            mock_tui_class.return_value = mock_tui
                            with patch("builtins.input", return_value="1"):
                                main()

        # TUI should be created with analysis_context=None
        call_kwargs = mock_tui_class.call_args[1]
        assert call_kwargs["analysis_context"] is None

    def test_tui_registers_analysis_commands(self) -> None:
        """TUI should have /summary and /analyze commands registered."""
        import os
        import sys

        from examples.repo import main

        mock_result = MagicMock()
        mock_result.status = "unchanged"
        mock_result.files_ingested = 10
        mock_result.project = MagicMock()
        mock_result.project.project_id = "test-project"

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["test-project"]
        mock_ananta.check_repo_for_updates.return_value = mock_result
        mock_ananta.get_analysis.return_value = None

        with patch.object(sys, "argv", ["repo.py"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with patch("examples.repo.AnantaTUI") as mock_tui_class:
                            mock_tui = MagicMock()
                            mock_tui_class.return_value = mock_tui
                            with patch("builtins.input", return_value="1"):
                                main()

        # Should register /summary and /analyze commands
        register_calls = mock_tui.register_command.call_args_list
        registered_names = [call[0][0] for call in register_calls]
        assert "/summary" in registered_names
        assert "/analyze" in registered_names

    def test_show_picker_shows_missing_marker(self, capsys: pytest.CaptureFixture[str]) -> None:
        """show_picker marks projects with missing local repos."""
        from ananta import ProjectInfo
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = ["remote-repo", "missing-local"]
        mock_ananta.get_project_info.side_effect = [
            ProjectInfo("remote-repo", "https://github.com/org/repo", False, True),
            ProjectInfo("missing-local", "/old/path", True, False),
        ]

        with patch("builtins.input", return_value="1"):
            show_picker(mock_ananta)

        captured = capsys.readouterr()
        assert "missing-local (missing - /old/path)" in captured.out

    def test_show_picker_handles_delete_command(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker handles 'd<N>' delete commands."""
        from ananta import ProjectInfo
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        # First call: show list with 2 items, user enters 'd1'
        # Second call: show list with 1 item, user enters '1'
        mock_ananta.list_projects.side_effect = [
            ["project-a", "project-b"],
            ["project-b"],
        ]
        mock_ananta.get_project_info.side_effect = [
            ProjectInfo("project-a", "https://github.com/org/a", False, True),
            ProjectInfo("project-b", "https://github.com/org/b", False, True),
            # After deletion:
            ProjectInfo("project-b", "https://github.com/org/b", False, True),
        ]

        inputs = iter(["d1", "y", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = show_picker(mock_ananta)

        mock_ananta.delete_project.assert_called_once_with("project-a")
        assert result == ("project-b", True)
        captured = capsys.readouterr()
        assert "Deleted 'project-a'" in captured.out

    def test_show_picker_delete_with_confirmation_no(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker cancels delete when user says no."""
        from ananta import ProjectInfo
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.side_effect = [
            ["project-a"],
            ["project-a"],
        ]
        mock_ananta.get_project_info.return_value = ProjectInfo(
            "project-a", "https://github.com/org/a", False, True
        )

        inputs = iter(["d1", "n", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = show_picker(mock_ananta)

        mock_ananta.delete_project.assert_not_called()
        assert result == ("project-a", True)

    def test_show_picker_delete_local_project_shows_correct_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker shows correct confirmation message for local projects."""
        from ananta import ProjectInfo
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.side_effect = [
            ["local-project"],
            [],
        ]
        mock_ananta.get_project_info.return_value = ProjectInfo(
            "local-project", "/path/to/local", True, True
        )

        # Track all input prompts
        prompts: list[str] = []

        def mock_input(prompt: str) -> str:
            prompts.append(prompt)
            if "d<N>" in prompt:
                return "d1"
            return "y"

        monkeypatch.setattr("builtins.input", mock_input)

        # After deletion, no projects remain so returns None
        show_picker(mock_ananta)

        # Local projects shouldn't mention "cloned repository"
        confirmation_prompt = prompts[1]  # Second prompt is the confirmation
        assert "indexed data" in confirmation_prompt
        assert "cloned repository" not in confirmation_prompt

    def test_show_picker_delete_remote_project_shows_correct_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """show_picker shows correct confirmation message for remote projects."""
        from ananta import ProjectInfo
        from examples.repo import show_picker

        mock_ananta = MagicMock()
        mock_ananta.list_projects.side_effect = [
            ["remote-project"],
            [],
        ]
        mock_ananta.get_project_info.return_value = ProjectInfo(
            "remote-project", "https://github.com/org/repo", False, True
        )

        # Track all input prompts
        prompts: list[str] = []

        def mock_input(prompt: str) -> str:
            prompts.append(prompt)
            if "d<N>" in prompt:
                return "d1"
            return "y"

        monkeypatch.setattr("builtins.input", mock_input)

        show_picker(mock_ananta)

        # Remote projects should mention "cloned repository"
        confirmation_prompt = prompts[1]  # Second prompt is the confirmation
        assert "cloned repository" in confirmation_prompt

    def test_non_git_local_path_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Non-git local path should print clean error and exit."""
        import os
        import sys

        from ananta.exceptions import RepoIngestError
        from examples.repo import main

        mock_ananta = MagicMock()
        mock_ananta.list_projects.return_value = []
        mock_ananta.create_project_from_repo.side_effect = RepoIngestError(
            "/path/to/non-git",
            RuntimeError("'/path/to/non-git' is not a git repository"),
        )

        with patch.object(sys, "argv", ["repo.py", "/path/to/non-git"]):
            with patch.dict(os.environ, {"ANANTA_API_KEY": "test-key"}, clear=True):
                with patch("examples.repo.Ananta", return_value=mock_ananta):
                    with patch("examples.repo.AnantaConfig"):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not a git repository" in captured.out
        # Should NOT have traceback
        assert "Traceback" not in captured.out
