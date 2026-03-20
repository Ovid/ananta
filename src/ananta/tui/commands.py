"""Command registry for TUI slash commands."""

from collections.abc import Callable


class CommandRegistry:
    """Registry for slash commands with optional command groups.

    Commands are registered with a name (e.g., "/help"), a handler callable,
    and a description. The handler receives the argument string (everything
    after the command name, stripped).

    Command groups (e.g., "/topic") have subcommands (e.g., "list", "switch").
    When a group is invoked without a subcommand, the group's help handler runs.
    When invoked with an unknown subcommand, the help handler also runs.
    """

    def __init__(self) -> None:
        self._commands: dict[str, tuple[Callable[[str], object], str, bool, str]] = {}
        self._groups: dict[
            str,
            tuple[
                str,
                Callable[[str], object],
                dict[str, tuple[Callable[[str], object], str, bool]],
            ],
        ] = {}

    def register(
        self,
        name: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
        usage: str = "",
    ) -> None:
        """Register a slash command."""
        self._commands[name] = (handler, description, threaded, usage)

    def register_group(self, name: str, description: str) -> None:
        """Register a command group (e.g., '/topic')."""
        subcommands: dict[str, tuple[Callable[[str], object], str, bool]] = {}

        def help_handler(args: str) -> None:
            pass  # Placeholder; actual display done by caller via list_subcommands()

        self._groups[name] = (description, help_handler, subcommands)

    def set_group_help_handler(self, name: str, handler: Callable[[str], object]) -> None:
        """Set a custom help handler for a group (replaces auto-generated one)."""
        if name not in self._groups:
            raise ValueError(f"Unknown group: {name}")
        desc, _old_handler, subcommands = self._groups[name]
        self._groups[name] = (desc, handler, subcommands)

    def register_subcommand(
        self,
        group: str,
        subcommand: str,
        handler: Callable[[str], object],
        description: str,
        *,
        threaded: bool = False,
    ) -> None:
        """Register a subcommand under a group."""
        if group not in self._groups:
            raise ValueError(f"Unknown group: {group}")
        _desc, _help, subcommands = self._groups[group]
        subcommands[subcommand] = (handler, description, threaded)

    def list_commands(self) -> list[tuple[str, str]]:
        """Return list of (name, description) tuples, sorted by name.

        Groups appear as top-level entries; individual subcommands do not.
        """
        items: list[tuple[str, str]] = []
        for name, (_handler, desc, _threaded, _usage) in self._commands.items():
            items.append((name, desc))
        for name, (desc, _help, _subs) in self._groups.items():
            items.append((name, desc))
        return sorted(items)

    def list_commands_with_usage(self) -> list[tuple[str, str, str]]:
        """Return (name, usage, description) tuples for all top-level commands/groups."""
        items: list[tuple[str, str, str]] = []
        for name, (_handler, desc, _threaded, usage) in self._commands.items():
            items.append((name, usage, desc))
        for name, (desc, _help, _subs) in self._groups.items():
            items.append((name, "<subcommand>", desc))
        return sorted(items)

    def list_subcommands(self, group: str) -> list[tuple[str, str]]:
        """Return sorted (subcommand_name, description) tuples for a group."""
        if group not in self._groups:
            return []
        _desc, _help, subcommands = self._groups[group]
        return sorted((name, desc) for name, (_handler, desc, _threaded) in subcommands.items())

    def is_group(self, name: str) -> bool:
        """Check if name is a registered command group."""
        return name in self._groups

    def resolve(self, text: str) -> tuple[Callable[[str], object], str, bool] | None:
        """Resolve a command string to (handler, args, threaded) without executing."""
        text = text.strip()
        parts = text.split(maxsplit=1)
        if not parts:
            return None
        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        if cmd_name in self._groups:
            _desc, help_handler, subcommands = self._groups[cmd_name]
            if not args:
                return help_handler, "", False
            sub_parts = args.split(maxsplit=1)
            sub_name = sub_parts[0]
            sub_args = sub_parts[1] if len(sub_parts) > 1 else ""
            if sub_name in subcommands:
                handler, _sub_desc, threaded = subcommands[sub_name]
                return handler, sub_args, threaded
            return help_handler, args, False

        if cmd_name not in self._commands:
            return None
        handler, _desc, threaded, _usage = self._commands[cmd_name]
        return handler, args, threaded

    def dispatch(self, text: str) -> bool:
        """Dispatch a command string. Returns True if command was found."""
        result = self.resolve(text)
        if result is None:
            return False
        handler, args, _threaded = result
        handler(args)
        return True

    def is_command(self, text: str) -> bool:
        """Check if text looks like a slash command."""
        return text.strip().startswith("/")

    def completions(self, prefix: str) -> list[tuple[str, str]]:
        """Return matching commands for auto-complete (top-level only)."""
        prefix = prefix.strip()
        items: list[tuple[str, str]] = []
        for name, (_handler, desc, _threaded, _usage) in self._commands.items():
            if name.startswith(prefix):
                items.append((name, desc))
        for name, (desc, _help, _subs) in self._groups.items():
            if name.startswith(prefix):
                items.append((name, desc))
        return sorted(items)

    def subcommand_completions(self, group: str, prefix: str) -> list[tuple[str, str]]:
        """Return matching subcommands for a group, filtered by prefix."""
        if group not in self._groups:
            return []
        _desc, _help, subcommands = self._groups[group]
        return sorted(
            (name, desc)
            for name, (_handler, desc, _threaded) in subcommands.items()
            if name.startswith(prefix)
        )
