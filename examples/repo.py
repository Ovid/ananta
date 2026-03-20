#!/usr/bin/env python3
"""Interactive git repository explorer using Ananta.

This script provides an interactive TUI for exploring git repositories using
Ananta's Recursive Language Model (RLM) capabilities. It supports both remote
repositories (GitHub, GitLab, Bitbucket) and local git repos.

Features:
    - Interactive picker for previously indexed repositories
    - Automatic update detection and application
    - Textual-based TUI with rich output, progress tracking, and token stats
    - Slash commands: /help, /write, /summary, /analyze, /clear, /quit
    - Session transcript export with /write command

Usage:
    # Explore a GitHub repository
    python examples/repo.py https://github.com/org/repo

    # Explore a local git repository
    python examples/repo.py /path/to/local/repo

    # Show picker of previously indexed repos
    python examples/repo.py

    # Auto-apply updates
    python examples/repo.py https://github.com/org/repo --update

    # Use a specific model
    python examples/repo.py --model gpt-4o

Environment Variables:
    ANANTA_API_KEY: Required. API key for your LLM provider.
    ANANTA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).
                  Overridden by --model flag.

Example:
    $ export ANANTA_API_KEY="your-api-key"
    $ python examples/repo.py https://github.com/Ovid/ananta
    Loading repository: https://github.com/Ovid/ananta
    Loaded 42 files.

    Ask questions about the codebase. Type /help for commands.

    > How does the sandbox execute code?
    [Thought for 15 seconds]
    The sandbox executes code in isolated Docker containers...

    # Save session transcript
    > /write                    # Auto-generates timestamped filename
    > /write my-notes.md        # Custom filename
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Allow importing script_utils whether running as a script or as a module.
# When run directly (python examples/repo.py), Python adds examples/ to sys.path
# automatically, so "from script_utils import" works. But when imported as a module
# (from examples.repo import ...), examples/ isn't in sys.path. This ensures
# script_utils is always findable, avoiding duplicate import lists for each mode.
sys.path.insert(0, str(Path(__file__).parent))

from script_utils import (
    format_analysis_as_context,
    format_analysis_for_display,
    install_urllib3_cleanup_hook,
    is_exit_command,
)

from ananta import Ananta, AnantaConfig
from ananta.exceptions import ProjectNotFoundError, RepoIngestError

# Guard TUI imports: textual is an optional dependency (ananta[tui]).
try:
    from ananta.tui import AnantaTUI
    from ananta.tui.widgets.output_area import OutputArea
except ModuleNotFoundError:
    if __name__ == "__main__":
        print("This example requires the TUI extra: pip install ananta[tui]")
        sys.exit(1)
    else:
        raise

# Storage path for repo projects (not "repos" - that collides with RepoIngester's subdirectory)
STORAGE_PATH = Path.home() / ".ananta" / "repo-explorer"

if TYPE_CHECKING:
    from ananta.models import RepoProjectResult


def _looks_like_repo_url_or_path(value: str) -> bool:
    """Check if value looks like a repository URL or filesystem path.

    Args:
        value: User input string to validate.

    Returns:
        True if value looks like a URL or path, False otherwise.
    """
    # URLs
    if value.startswith(("http://", "https://", "git@")):
        return True
    # Absolute paths
    if value.startswith("/"):
        return True
    # Home-relative paths
    if value.startswith("~"):
        return True
    # Relative paths
    if value.startswith("./") or value.startswith("../"):
        return True
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Command line arguments. If None, uses sys.argv.

    Returns:
        Parsed arguments namespace with:
            - repo: Git repository URL or local path (optional)
            - update: Whether to auto-apply updates without prompting
    """
    parser = argparse.ArgumentParser(description="Explore git repositories using Ananta RLM")
    parser.add_argument(
        "repo",
        nargs="?",
        help="Git repository URL or local path (shows picker if omitted)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Auto-apply updates without prompting",
    )
    parser.add_argument(
        "--pristine",
        action="store_true",
        help="Skip using pre-computed analysis as query context",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=None,
        help=(
            "Run post-analysis semantic verification. Produces higher-accuracy "
            "results by adversarially reviewing all findings. Note: this can "
            "significantly increase analysis time and token count "
            "(typically 1-2 additional LLM calls)."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        help="LLM model name (overrides ANANTA_MODEL env var)",
    )
    return parser.parse_args(argv)


def show_picker(ananta: Ananta) -> tuple[str, bool] | None:
    """Show interactive repository picker for previously indexed repos.

    Displays a numbered list of previously indexed repositories and prompts
    the user to either select one by number, delete one with 'd<N>', or
    enter a new URL/path.

    Args:
        ananta: Initialized Ananta instance to query for existing projects.

    Returns:
        None: If no projects exist in storage.
        tuple[str, True]: If user selected an existing project (project name).
        tuple[str, False]: If user entered a new URL/path to index.

    Example:
        Available repositories:
          1. org-repo
          2. another-project (missing - /old/path)

        Enter number, 'd<N>' to delete, or new URL: 1
        -> Returns ("org-repo", True)

        Enter number, 'd<N>' to delete, or new URL: https://github.com/new/repo
        -> Returns ("https://github.com/new/repo", False)
    """
    while True:
        projects = ananta.list_projects()
        if not projects:
            return None

        print("Available repositories:")
        project_infos = []
        for i, name in enumerate(projects, 1):
            info = ananta.get_project_info(name)
            project_infos.append(info)
            if info.is_local and not info.source_exists:
                print(f"  {i}. {name} (missing - {info.source_url})")
            else:
                print(f"  {i}. {name}")
        print()

        user_input = input("Enter number, 'd<N>' to delete, or new URL: ").strip()

        # Check for delete command
        if user_input.lower().startswith("d"):
            try:
                num = int(user_input[1:])
                if 1 <= num <= len(projects):
                    project_name = projects[num - 1]
                    info = project_infos[num - 1]

                    # Determine confirmation message
                    if info.is_local or info.source_url is None:
                        msg = f"Delete '{project_name}'? This will remove all indexed data. (y/n): "
                    else:
                        msg = (
                            f"Delete '{project_name}'? "
                            "This will remove indexed data and cloned repository. (y/n): "
                        )

                    confirm = input(msg).strip().lower()
                    if confirm == "y":
                        ananta.delete_project(project_name)
                        print(f"Deleted '{project_name}'.")
                    print()
                    continue  # Re-show picker
            except ValueError:
                pass  # Not a valid "d<N>" command, fall through to other handlers

        # Check if it's a number selecting an existing project
        try:
            num = int(user_input)
            if 1 <= num <= len(projects):
                return (projects[num - 1], True)
        except ValueError:
            pass  # Not a number, treat as URL/path below

        # Check for exit commands
        if is_exit_command(user_input):
            return ("", False)

        # Validate that input looks like a URL or path
        if _looks_like_repo_url_or_path(user_input):
            return (user_input, False)

        # Invalid input - show error and reprompt
        print(f"Invalid input: '{user_input}'")
        print("Enter a number, 'd<N>' to delete, URL, or local path.")
        print()


def prompt_for_repo() -> str:
    """Prompt user to enter a repository URL or local path.

    Called when no previously indexed repositories exist, prompting the user
    to provide a new repository to index.

    Returns:
        User-provided repository URL or local filesystem path, stripped of
        leading/trailing whitespace.
    """
    print("No repositories loaded yet.")
    return input("Enter repo URL or local path: ").strip()


def handle_updates(result: RepoProjectResult, auto_update: bool) -> RepoProjectResult:
    """Handle repository update detection and application.

    When a repository has been previously indexed and changes are detected
    (new commits), this function either automatically applies updates or
    prompts the user for confirmation.

    Args:
        result: The result from create_project_from_repo() containing the
            project and its current status.
        auto_update: If True, applies updates without prompting. If False,
            asks the user whether to apply available updates.

    Returns:
        The original result if no updates were available or user declined,
        or a new RepoProjectResult with updated files if updates were applied.
    """
    if result.status != "updates_available":
        return result

    if auto_update:
        print("Applying updates...")
        return result.apply_updates()

    print(f"Updates available for {result.project.project_id}.")
    response = input("Apply updates? (y/n): ").strip().lower()

    if response == "y":
        print("Applying updates...")
        return result.apply_updates()

    return result


def check_and_prompt_analysis(ananta: Ananta, project_id: str) -> None:
    """Check analysis status and prompt user if needed.

    Args:
        ananta: Ananta instance.
        project_id: Project to check.
    """
    try:
        status = ananta.get_analysis_status(project_id)
    except ProjectNotFoundError:
        return  # Project may not exist yet; skip analysis check gracefully

    if status == "missing":
        print("Note: No codebase analysis exists for this repository.")
        try:
            response = input("Generate analysis? (y/n): ").strip().lower()
            if response == "y":
                print("Generating analysis (this may take a minute)...")
                analysis = ananta.generate_analysis(project_id)
                print("Analysis complete.\n")
                print(format_analysis_for_display(analysis))
                print()
        except (EOFError, KeyboardInterrupt):
            print()  # Clean line after interrupt
    elif status == "stale":
        print("Note: Codebase analysis is outdated (HEAD has moved).")
        try:
            response = input("Regenerate analysis? (y/n): ").strip().lower()
            if response == "y":
                print("Regenerating analysis...")
                analysis = ananta.generate_analysis(project_id)
                print("Analysis updated.\n")
                print(format_analysis_for_display(analysis))
                print()
        except (EOFError, KeyboardInterrupt):
            print()  # Clean line after interrupt


def main() -> None:
    """Main entry point for the repository explorer CLI.

    Orchestrates the complete workflow:
    1. Validates environment (ANANTA_API_KEY required)
    2. Initializes Ananta with storage configuration
    3. Determines repository source (argument, picker, or prompt)
    4. Loads or creates the repository project
    5. Handles any available updates
    6. Launches the TUI for interactive querying

    Raises:
        SystemExit: If ANANTA_API_KEY is not set or Docker is unavailable.
    """
    install_urllib3_cleanup_hook()
    args = parse_args()

    if not os.environ.get("ANANTA_API_KEY"):
        print("Error: ANANTA_API_KEY environment variable not set.")
        print()
        print("Environment variables:")
        print("  ANANTA_API_KEY   (required) API key for your LLM provider")
        print("  ANANTA_MODEL     (optional) Model name, e.g.:")
        print("                   - claude-sonnet-4-20250514 (default, Anthropic)")
        print("                   - gpt-4o (OpenAI)")
        print("                   - gemini/gemini-1.5-pro (Google)")
        print()
        print("The provider is auto-detected from the model name via LiteLLM.")
        sys.exit(1)

    config = AnantaConfig.load(storage_path=STORAGE_PATH, verify=args.verify, model=args.model)
    try:
        ananta = Ananta(config=config)
    except RuntimeError as e:
        if "Docker" in str(e):
            print(f"Error: {e}")
            print()
            print("To build the sandbox container, run:")
            print("  docker build -t ananta-sandbox sandbox/")
            sys.exit(1)
        raise

    # Determine which repo to use
    project = None
    if args.repo:
        repo_url = args.repo
    else:
        # Interactive picker mode
        picker_result = show_picker(ananta)
        if picker_result is None:
            repo_url = prompt_for_repo()
        elif picker_result[1]:
            # User selected existing project by number - check for updates
            project_name = picker_result[0]
            print(f"Loading project: {project_name}")
            result = ananta.check_repo_for_updates(project_name)

            # Handle status
            if result.status == "unchanged":
                print(f"Using cached repository ({result.files_ingested} files).")

            result = handle_updates(result, args.update)

            if result.status == "created":
                print(f"Updated: {result.files_ingested} files.")

            project = result.project
        else:
            # User entered a new URL/path
            repo_url = picker_result[0]

        if project is None and not repo_url:
            print("No repository specified. Exiting.")
            sys.exit(0)

    # Load or create project from URL if not already loaded
    if project is None:
        print(f"Loading repository: {repo_url}")
        try:
            result = ananta.create_project_from_repo(repo_url)
        except RepoIngestError as e:
            print(f"Error: {e}")
            sys.exit(1)

        # Handle status
        if result.status == "created":
            print(f"Loaded {result.files_ingested} files.")
        elif result.status == "unchanged":
            print(f"Using cached repository ({result.files_ingested} files).")

        result = handle_updates(result, args.update)

        if result.status == "created":
            print(f"Updated: {result.files_ingested} files.")

        project = result.project

    # Check analysis status
    check_and_prompt_analysis(ananta, project.project_id)

    # Load analysis context for query injection
    analysis_context = None
    if not args.pristine:
        analysis = ananta.get_analysis(project.project_id)
        if analysis:
            analysis_context = format_analysis_as_context(analysis)

    # Create and launch TUI
    model = args.model or os.environ.get("ANANTA_MODEL", "claude-sonnet-4-20250514")
    api_key = os.environ.get("ANANTA_API_KEY")
    tui = AnantaTUI(
        project=project,
        project_name=project.project_id,
        analysis_context=analysis_context,
        model=model,
        api_key=api_key,
    )

    # Register custom commands
    def handle_summary(args: str) -> None:
        analysis = ananta.get_analysis(project.project_id)
        if analysis is None:
            tui.query_one(OutputArea).add_system_message(
                "No analysis. Use /analyze to generate."
            )
        else:
            tui.query_one(OutputArea).add_system_markdown(
                format_analysis_for_display(analysis)
            )

    def _post_message(msg: str) -> None:
        """Post a system message to the output area (thread-safe)."""
        tui.call_from_thread(
            tui.query_one(OutputArea).add_system_message, msg
        )

    def handle_analyze(args: str) -> None:
        _post_message("Generating analysis...")
        try:
            ananta.generate_analysis(project.project_id)
            _post_message("Analysis complete. Use /summary to view.")
        except Exception as e:
            _post_message(f"Error: {e}")

    def handle_clear(args: str) -> None:
        tui._session.clear_history()
        tui.query_one(OutputArea).clear()

    tui.register_command("/summary", handle_summary, "Show codebase analysis")
    tui.register_command(
        "/analyze", handle_analyze, "Generate/regenerate analysis", threaded=True
    )
    tui.register_command("/clear", handle_clear, "Clear conversation history")
    tui.run()
    print("Cleaning up containers...")


if __name__ == "__main__":
    main()
