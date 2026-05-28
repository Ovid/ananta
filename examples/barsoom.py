#!/usr/bin/env python3
"""Interactive Barsoom novel explorer using Ananta.

This script provides an interactive CLI for exploring Edgar Rice Burroughs'
Barsoom (Mars) novel series using Ananta's Recursive Language Model (RLM)
capabilities. The novels are in the public domain and included in the
test-datasets directory.

The Barsoom series consists of 7 novels:
    1. A Princess of Mars
    2. The Gods of Mars
    3. The Warlord of Mars
    4. Thuvia, Maid of Mars
    5. The Chessmen of Mars
    6. The Master Mind of Mars
    7. A Fighting Man of Mars

Features:
    - Automatic setup on first run (uploads all 7 novels)
    - Conversation history for follow-up questions
    - Session transcript export with /write command
    - Slash commands: /help, /write, /clear, /quit
    - Real-time progress and token stats in the info bar
    - Non-interactive mode for scripted queries

Usage:
    # Interactive mode (sets up on first run)
    python examples/barsoom.py

    # Re-upload novels (prompts for confirmation if project already exists)
    python examples/barsoom.py --setup

    # Re-upload non-interactively (e.g. scripted): --force skips the prompt
    python examples/barsoom.py --setup --force

    # Single query (non-interactive); requires --force with --setup on re-runs
    python examples/barsoom.py --prompt "Who is Dejah Thoris?"

    # Use a specific model
    python examples/barsoom.py --model gpt-4o

Environment Variables:
    ANANTA_API_KEY: Required. API key for your LLM provider.
    ANANTA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).
                  Overridden by --model flag.

Example:
    $ export ANANTA_API_KEY="your-api-key"
    $ python examples/barsoom.py
    Setting up Barsoom project...
    Uploading: A Princess of Mars (barsoom-1.txt)
    ...
    Setup complete! 7 novels loaded.

    Ask questions about the Barsoom series. Type /help for commands.

    > Who is the son of Dejah Thoris?
    [Thought for 29 seconds]
    The son of Dejah Thoris and John Carter is **Carthoris of Helium**.

    # Save session transcript
    > /write                    # Auto-generates timestamped filename
    > /write my-research.md     # Custom filename
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Allow importing script_utils whether running as a script or as a module.
# When run directly (python examples/barsoom.py), Python adds examples/ to sys.path
# automatically, so "from script_utils import" works. But when imported as a module
# (from examples.barsoom import ...), examples/ isn't in sys.path. This ensures
# script_utils is always findable, avoiding duplicate import lists for each mode.
sys.path.insert(0, str(Path(__file__).parent))

from script_utils import (
    ThinkingSpinner,
    format_progress,
    format_stats,
    format_thought_time,
    format_verified_output,
    install_urllib3_cleanup_hook,
)

from ananta import Ananta
from ananta.config import AnantaConfig
from ananta.exceptions import ProjectNotFoundError
from ananta.rlm.trace import StepType, TokenUsage

# Guard TUI import: textual is an optional dependency (ananta[tui]).
try:
    from ananta.tui import AnantaTUI
    from ananta.tui.widgets.output_area import OutputArea
except ModuleNotFoundError:
    if __name__ == "__main__":
        print("This example requires the TUI extra: pip install ananta[tui]")
        sys.exit(1)
    else:
        raise

BOOKS = {
    "barsoom-1.txt": "A Princess of Mars",
    "barsoom-2.txt": "The Gods of Mars",
    "barsoom-3.txt": "The Warlord of Mars",
    "barsoom-4.txt": "Thuvia, Maid of Mars",
    "barsoom-5.txt": "The Chessmen of Mars",
    "barsoom-6.txt": "The Master Mind of Mars",
    "barsoom-7.txt": "A Fighting Man of Mars",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments and validate environment configuration.

    This function sets up the CLI parser, processes flags, and ensures the
    required environment variables for the LLM providers are configured.
    If the selected model is an Ollama model, ANANTA_API_KEY is automatically
    mocked to 'ollama'.

    Args:
        argv: Command-line arguments. If None, uses sys.argv.

    Returns:
        Parsed arguments namespace with:
            - setup (bool): Force re-upload of novels even if project exists.
            - prompt (str | None): Single query for non-interactive mode.
            - verify (bool | None): Enable semantic verification of results.
            - model (str): LLM model name to execute against.
            - ANANTA_API_KEY (str): Resolved API key for the LLM provider.

    Raises:
        SystemExit: If required arguments or environment variables are missing.
    """
    parser = argparse.ArgumentParser(
        description="Interactive Barsoom novel explorer using Ananta."
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help=(
            "Re-upload the novels. Prompts for confirmation if the project "
            "already exists; pass --force to skip the prompt (required for "
            "scripted/--prompt runs)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip the --setup confirmation prompt when overwriting an existing project.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Run a single query and exit (non-interactive mode)",
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
        default=os.environ.get("ANANTA_MODEL") or "claude-sonnet-4-20250514",
        help="LLM model name (overrides the ANANTA_MODEL environment variable)",
    )
    env_group = parser.add_argument_group("environment variables")
    env_group.add_argument(
        dest=argparse.SUPPRESS, # Documentation.
        metavar="ANANTA_API_KEY",
        nargs="?",
        default=os.environ.get("ANANTA_API_KEY"),
        help="Required. API key for your LLM provider."
    )
    env_group.add_argument(
        dest=argparse.SUPPRESS, # Documentation. The actual argument is parsed in --model.
        metavar="ANANTA_MODEL",
        nargs="?",
        help=(
            "Optional. Model name (default: claude-sonnet-4-20250514). "
            "Overridden by --model flag. Examples: claude-sonnet-4-20250514, "
            "gpt-4o, gemini/gemini-1.5-pro, ollama/llama3.1. "
            "The provider will be auto-detected by LiteLLM."
        )
    )

    args = parser.parse_args(argv)

    # Check for API key
    if args.model.startswith("ollama/"):
        os.environ["ANANTA_API_KEY"] = "ollama"
        args.__setattr__("ANANTA_API_KEY", "ollama")

    if os.environ["ANANTA_API_KEY"] is None:
        parser.error("Error: ANANTA_API_KEY environment variable not set.")

    return args


STORAGE_PATH = "./barsoom_data"
PROJECT_NAME = "barsoom"


def get_datasets_dir() -> Path:
    """Get the path to the Barsoom test datasets directory.

    Returns:
        Path to the test-datasets/barsoom directory, relative to this script's
        location. The directory contains the 7 Barsoom novels as .txt files.
    """
    return Path(__file__).parent.parent / "test-datasets" / "barsoom"


def confirm_overwrite(project_name: str, *, force: bool, interactive: bool) -> bool:
    """Decide whether to delete and re-upload an existing project.

    Args:
        project_name: Project that already exists on disk.
        force: True if the user passed --force; skips the prompt.
        interactive: True if it is safe to call input() (TTY, no --prompt).

    Returns:
        True if the caller should delete and recreate the project.
        False if the caller should keep the existing project.

    Raises:
        SystemExit: If --setup was requested on a non-interactive run without
            --force. Refusing to prompt avoids hanging scripted invocations
            (e.g. `--prompt`) on stdin.
    """
    if force:
        return True
    if not interactive:
        print(
            f"Error: Project '{project_name}' already exists. "
            "Pass --force to overwrite it in non-interactive mode, "
            "or omit --setup to use the existing project.",
            file=sys.stderr,
        )
        sys.exit(1)
    response = input(f"Project '{project_name}' exists. Delete and re-upload? [y/N] ")
    return response.strip().lower() in ("y", "yes")


def setup_project(ananta: Ananta) -> None:
    """Set up the Barsoom project by uploading all 7 novels.

    Creates a new project named "barsoom" and uploads each novel from the
    test-datasets directory. Progress is printed for each file uploaded.

    Args:
        ananta: Initialized Ananta instance to create the project in.

    Note:
        Assumes the "barsoom" project does not already exist; the caller is
        responsible for deleting any prior project first (see
        `confirm_overwrite`). The novels total approximately 2.8 million
        characters across all 7 books.
    """
    print("Setting up Barsoom project...")
    project = ananta.create_project(PROJECT_NAME)
    datasets_dir = get_datasets_dir()

    for filename, title in BOOKS.items():
        filepath = datasets_dir / filename
        print(f"Uploading: {title} ({filename})")
        project.upload(filepath)

    print(f"Setup complete! {len(BOOKS)} novels loaded.")


def main() -> None:
    """Main entry point for the Barsoom explorer CLI.

    Orchestrates the complete workflow:
    1. Installs clean-up hooks and parses command-line arguments.
    2. Initializes Ananta configuration and backend clients.
    3. Triggers initial project setup on first run or if forced via --setup;
       if --setup is passed against an existing project, prompts before deleting
       and re-uploading (or skips the prompt with --force)
    4. Handles single query (--prompt) or launches TUI for interactive mode

    Raises:
        SystemExit: If the target project cannot be found or an error occurs 
                    during prompt execution.
    """
    install_urllib3_cleanup_hook()
    args = parse_args()

    # Initialize Ananta with config from environment
    config = AnantaConfig.load(storage_path=STORAGE_PATH, verify=args.verify, model=args.model)
    ananta = Ananta(config=config)

    # Check if project exists
    project_exists = PROJECT_NAME in ananta.list_projects()

    # Setup if needed. If --setup was passed against an existing project, gate
    # the destructive overwrite behind a confirmation (or --force for scripts).
    if not project_exists:
        setup_project(ananta)
    elif args.setup:
        interactive = args.prompt is None
        if confirm_overwrite(PROJECT_NAME, force=args.force, interactive=interactive):
            print(f"Removing existing '{PROJECT_NAME}' project...")
            ananta.delete_project(PROJECT_NAME)
            setup_project(ananta)
        else:
            print(f"Keeping existing '{PROJECT_NAME}' project.")

    # Get the project
    try:
        project = ananta.get_project(PROJECT_NAME)
    except ProjectNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Non-interactive mode with --prompt
    if args.prompt:
        try:
            spinner = ThinkingSpinner()
            spinner.start()
            query_start_time = time.time()

            def on_progress(step_type: StepType, iteration: int, content: str, _: TokenUsage) -> None:
                spinner.stop()
                elapsed = time.time() - query_start_time
                print(format_progress(step_type, iteration, content, elapsed_seconds=elapsed))
                spinner.start()

            result = project.query(args.prompt, on_progress=on_progress)
            spinner.stop()

            elapsed = time.time() - query_start_time
            print(format_thought_time(elapsed))
            if result.semantic_verification is not None:
                print(format_verified_output(result.answer, result.semantic_verification))
            else:
                print(result.answer)
            print()

            print(format_stats(result.execution_time, result.token_usage, result.trace))
            print()

        except Exception as e:
            spinner.stop()
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Interactive mode - launch TUI
    tui = AnantaTUI(project=project, project_name=PROJECT_NAME, model=config.model)

    def handle_clear(args: str) -> None:
        tui._session.clear_history()
        tui.query_one(OutputArea).clear()

    tui.register_command("/clear", handle_clear, "Clear conversation history")
    tui.run()
    print("Cleaning up containers...")


if __name__ == "__main__":
    main()
