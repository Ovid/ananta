"""Tests for TUI command registry."""

import re

import pytest

from ananta.tui.commands import CommandRegistry
from ananta.tui.widgets.completion_popup import CompletionPopup


class TestCommandRegistry:
    """Tests for CommandRegistry."""

    def test_register_and_list(self) -> None:
        """Registered commands appear in list."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Show help")
        commands = registry.list_commands()
        assert len(commands) == 1
        assert commands[0] == ("/help", "Show help")

    def test_dispatch_calls_handler(self) -> None:
        """Dispatch calls the correct handler."""
        called_with: list[str] = []
        registry = CommandRegistry()
        registry.register("/echo", lambda args: called_with.append(args), "Echo args")
        registry.dispatch("/echo hello world")
        assert called_with == ["hello world"]

    def test_dispatch_no_args(self) -> None:
        """Dispatch with no args passes empty string."""
        called_with: list[str] = []
        registry = CommandRegistry()
        registry.register("/help", lambda args: called_with.append(args), "Help")
        registry.dispatch("/help")
        assert called_with == [""]

    def test_dispatch_unknown_command_returns_false(self) -> None:
        """Dispatch returns False for unknown commands."""
        registry = CommandRegistry()
        result = registry.dispatch("/unknown")
        assert result is False

    def test_dispatch_known_command_returns_true(self) -> None:
        """Dispatch returns True for known commands."""
        registry = CommandRegistry()
        registry.register("/help", lambda args: None, "Help")
        result = registry.dispatch("/help")
        assert result is True

    def test_is_command_with_slash(self) -> None:
        """Strings starting with / are commands."""
        registry = CommandRegistry()
        assert registry.is_command("/help") is True

    def test_is_command_without_slash(self) -> None:
        """Regular text is not a command."""
        registry = CommandRegistry()
        assert registry.is_command("hello") is False

    def test_is_command_with_leading_whitespace(self) -> None:
        """Leading whitespace before / is still a command."""
        registry = CommandRegistry()
        assert registry.is_command("  /help") is True

    def test_completions_empty_prefix(self) -> None:
        """Completions with just / returns all commands."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Help")
        registry.register("/write", lambda _: None, "Write")
        completions = registry.completions("/")
        assert set(completions) == {("/help", "Help"), ("/write", "Write")}

    def test_completions_partial_prefix(self) -> None:
        """Completions filters by prefix."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Help")
        registry.register("/write", lambda _: None, "Write")
        completions = registry.completions("/he")
        assert completions == [("/help", "Help")]

    def test_dispatch_strips_leading_whitespace(self) -> None:
        """Dispatch handles leading whitespace before /."""
        called: list[bool] = []
        registry = CommandRegistry()
        registry.register("/help", lambda args: called.append(True), "Help")
        result = registry.dispatch("  /help")
        assert result is True
        assert called == [True]

    def test_register_threaded_command(self) -> None:
        """Commands can be registered as threaded."""
        registry = CommandRegistry()
        registry.register("/analyze", lambda _: None, "Analyze", threaded=True)
        result = registry.resolve("/analyze")
        assert result is not None
        _handler, _args, threaded = result
        assert threaded is True

    def test_resolve_non_threaded_command(self) -> None:
        """Non-threaded commands resolve with threaded=False."""
        registry = CommandRegistry()
        registry.register("/help", lambda _: None, "Help")
        result = registry.resolve("/help")
        assert result is not None
        _handler, _args, threaded = result
        assert threaded is False

    def test_resolve_with_args(self) -> None:
        """Resolve parses command name and args."""
        registry = CommandRegistry()
        registry.register("/write", lambda _: None, "Write")
        result = registry.resolve("/write output.md")
        assert result is not None
        _handler, args, _threaded = result
        assert args == "output.md"

    def test_resolve_unknown_returns_none(self) -> None:
        """Resolve returns None for unknown commands."""
        registry = CommandRegistry()
        result = registry.resolve("/unknown")
        assert result is None

    def test_resolve_calls_handler(self) -> None:
        """Resolve returns a callable handler."""
        called_with: list[str] = []
        registry = CommandRegistry()
        registry.register("/echo", lambda a: called_with.append(a), "Echo")
        result = registry.resolve("/echo hello")
        assert result is not None
        handler, args, _threaded = result
        handler(args)
        assert called_with == ["hello"]


class TestCommandGroupRegistration:
    """Tests for register_group and register_subcommand."""

    def test_register_group_appears_in_list_commands(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        commands = reg.list_commands()
        assert ("/topic", "Topic management") in commands

    def test_register_subcommand(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        called_with: list[str] = []
        reg.register_subcommand(
            "/topic", "list", lambda args: called_with.append(args), "List all topics"
        )
        names = [name for name, _ in reg.list_commands()]
        assert "/topic list" not in names

    def test_resolve_subcommand(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        called_with: list[str] = []
        reg.register_subcommand(
            "/topic", "switch", lambda args: called_with.append(args), "Switch topic"
        )
        result = reg.resolve("/topic switch my-topic")
        assert result is not None
        handler, args, threaded = result
        handler(args)
        assert called_with == ["my-topic"]

    def test_resolve_subcommand_no_args(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        called_with: list[str] = []
        reg.register_subcommand(
            "/topic", "list", lambda args: called_with.append(args), "List topics"
        )
        result = reg.resolve("/topic list")
        assert result is not None
        handler, args, threaded = result
        handler(args)
        assert called_with == [""]

    def test_resolve_bare_group_returns_help_handler(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "list", lambda args: None, "List all topics")
        result = reg.resolve("/topic")
        assert result is not None
        handler, args, threaded = result
        assert args == ""

    def test_resolve_unknown_subcommand_returns_help_handler(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "list", lambda args: None, "List topics")
        result = reg.resolve("/topic bogus")
        assert result is not None
        handler, args, threaded = result
        assert args == "bogus"

    def test_subcommand_threaded_flag(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "add", lambda args: None, "Add papers", threaded=True)
        result = reg.resolve("/topic add 1 2 3")
        assert result is not None
        _handler, _args, threaded = result
        assert threaded is True

    def test_list_subcommands(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")
        reg.register_subcommand("/topic", "add", lambda a: None, "Add papers")
        reg.register_subcommand("/topic", "list", lambda a: None, "List topics")
        subs = reg.list_subcommands("/topic")
        names = [name for name, _ in subs]
        assert names == ["add", "list", "switch"]

    def test_list_subcommands_unknown_group(self) -> None:
        reg = CommandRegistry()
        assert reg.list_subcommands("/bogus") == []

    def test_set_group_help_handler_raises_for_unknown_group(self) -> None:
        reg = CommandRegistry()
        with pytest.raises(ValueError, match="Unknown group"):
            reg.set_group_help_handler("/nonexistent", lambda a: None)


class TestCommandGroupCompletions:
    """Tests for two-level autocomplete with command groups."""

    def test_completions_top_level_includes_groups(self) -> None:
        reg = CommandRegistry()
        reg.register("/help", lambda a: None, "Show help")
        reg.register_group("/topic", "Topic management")
        completions = reg.completions("/")
        names = [name for name, _ in completions]
        assert "/help" in names
        assert "/topic" in names

    def test_completions_group_prefix_filters(self) -> None:
        reg = CommandRegistry()
        reg.register("/help", lambda a: None, "Show help")
        reg.register_group("/topic", "Topic management")
        completions = reg.completions("/to")
        assert len(completions) == 1
        assert completions[0][0] == "/topic"

    def test_subcommand_completions(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register_subcommand("/topic", "list", lambda a: None, "List topics")
        reg.register_subcommand("/topic", "switch", lambda a: None, "Switch topic")
        reg.register_subcommand("/topic", "create", lambda a: None, "Create topic")
        subs = reg.subcommand_completions("/topic", "")
        assert len(subs) == 3
        subs = reg.subcommand_completions("/topic", "sw")
        assert len(subs) == 1
        assert subs[0][0] == "switch"

    def test_subcommand_completions_unknown_group(self) -> None:
        reg = CommandRegistry()
        assert reg.subcommand_completions("/bogus", "") == []

    def test_is_group(self) -> None:
        reg = CommandRegistry()
        reg.register_group("/topic", "Topic management")
        reg.register("/help", lambda a: None, "Help")
        assert reg.is_group("/topic") is True
        assert reg.is_group("/help") is False
        assert reg.is_group("/bogus") is False


class TestCompletionPopupHeight:
    """Tests for CompletionPopup displaying all items."""

    def test_popup_max_height_fits_all_commands(self) -> None:
        """CompletionPopup max-height should accommodate at least 15 items."""
        popup = CompletionPopup()
        css = popup.DEFAULT_CSS
        match = re.search(r"max-height:\s*(\d+)", css)
        assert match is not None
        max_height = int(match.group(1))
        assert max_height >= 15, f"max-height {max_height} too small for 15+ commands"


class TestTwoLevelAutocomplete:
    """Tests for two-level autocomplete in AnantaTUI."""

    async def test_group_space_shows_subcommand_completions(self) -> None:
        """Typing '/topic ' shows subcommand completions."""
        from unittest.mock import MagicMock

        from ananta.tui import AnantaTUI
        from ananta.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = AnantaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand(
            "/topic", "switch", lambda a: None, "Switch topic"
        )

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic "
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is True
            rendered = str(popup.render())
            assert "list" in rendered
            assert "switch" in rendered

    async def test_group_space_prefix_filters_subcommands(self) -> None:
        """Typing '/topic sw' narrows to 'switch'."""
        from unittest.mock import MagicMock

        from ananta.tui import AnantaTUI
        from ananta.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = AnantaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand(
            "/topic", "switch", lambda a: None, "Switch topic"
        )

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic sw"
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is True
            rendered = str(popup.render())
            assert "switch" in rendered
            assert "list" not in rendered

    async def test_subcommand_accept_fills_group_and_subcommand(self) -> None:
        """Accepting a subcommand completion fills '/topic switch '."""
        from unittest.mock import MagicMock

        from ananta.tui import AnantaTUI
        from ananta.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = AnantaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand(
            "/topic", "switch", lambda a: None, "Switch topic"
        )

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic "
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            popup.select_next()  # Move from "list" to "switch"
            input_area.post_message(InputArea.CompletionAccept())
            await pilot.pause()
            assert input_area.text == "/topic switch "

    async def test_non_group_space_hides_popup(self) -> None:
        """Typing '/help ' (not a group) hides the popup."""
        from unittest.mock import MagicMock

        from ananta.tui import AnantaTUI
        from ananta.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = AnantaTUI(project=project, project_name="test")

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/help "
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is False

    async def test_exact_subcommand_hides_popup(self) -> None:
        """Typing '/topic list' exactly hides popup so Enter submits."""
        from unittest.mock import MagicMock

        from ananta.tui import AnantaTUI
        from ananta.tui.widgets.input_area import InputArea

        project = MagicMock()
        app = AnantaTUI(project=project, project_name="test")
        app._command_registry.register_group("/topic", "Topic management")
        app._command_registry.register_subcommand("/topic", "list", lambda a: None, "List topics")
        app._command_registry.register_subcommand(
            "/topic", "switch", lambda a: None, "Switch topic"
        )

        async with app.run_test() as pilot:
            input_area = pilot.app.query_one(InputArea)
            input_area.text = "/topic list"
            await pilot.pause()
            popup = pilot.app.query_one(CompletionPopup)
            assert popup.display is False
            assert input_area.completion_active is False


class TestCommandUsageHints:
    """Tests for usage hints in command registration."""

    def test_register_with_usage(self) -> None:
        """Commands can be registered with a usage string."""
        reg = CommandRegistry()
        reg.register("/search", lambda a: None, "Search arXiv", usage="<query> [--author, ...]")
        commands = reg.list_commands()
        assert ("/search", "Search arXiv") in commands

    def test_list_commands_with_usage(self) -> None:
        """list_commands_with_usage returns (name, usage, description) tuples."""
        reg = CommandRegistry()
        reg.register("/search", lambda a: None, "Search arXiv", usage="<query> [--author, ...]")
        reg.register("/quit", lambda a: None, "Exit")
        reg.register_group("/topic", "Topic management")
        result = reg.list_commands_with_usage()
        search_entry = next(e for e in result if e[0] == "/search")
        assert search_entry == ("/search", "<query> [--author, ...]", "Search arXiv")
        quit_entry = next(e for e in result if e[0] == "/quit")
        assert quit_entry == ("/quit", "", "Exit")
        topic_entry = next(e for e in result if e[0] == "/topic")
        assert topic_entry == ("/topic", "<subcommand>", "Topic management")
