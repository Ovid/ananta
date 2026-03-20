#!/usr/bin/env python3
"""Multi-repo PRD analysis using federated queries.

This script analyzes how a PRD (Product Requirements Document) impacts
multiple codebases and generates a draft HLD (High-Level Design).

Usage:
    # Interactive picker + paste PRD
    python examples/multi_repo.py

    # Interactive picker + PRD from file
    python examples/multi_repo.py --prd requirements.md

    # Explicit repos + PRD from file
    python examples/multi_repo.py repo1_url repo2_url --prd spec.md

    # Explicit repos + paste PRD
    python examples/multi_repo.py repo1_url repo2_url

Environment Variables:
    ANANTA_API_KEY: Required. API key for your LLM provider.
    ANANTA_MODEL: Optional. Model name (default: claude-sonnet-4-20250514).

Example:
    $ export ANANTA_API_KEY="your-api-key"
    $ python examples/multi_repo.py --prd my-feature.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from script_utils import install_urllib3_cleanup_hook

from ananta import Ananta, AnantaConfig
from ananta.experimental.multi_repo import AlignmentReport, MultiRepoAnalyzer

STORAGE_PATH = Path.home() / ".ananta" / "multi-repo"
EXPLORER_STORAGE_PATH = Path.home() / ".ananta" / "repo-explorer"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Analyze PRD impact across multiple repositories")
    parser.add_argument(
        "repos",
        nargs="*",
        help="Git repository URLs or local paths to analyze (shows picker if omitted)",
    )
    parser.add_argument(
        "--prd",
        help="Path to PRD markdown file (prompts for paste if omitted)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress during analysis",
    )
    return parser.parse_args(argv)


def read_multiline_input() -> str:
    """Read multiline input from stdin until EOF or blank line."""
    lines = []
    try:
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
    except EOFError:
        pass  # User pressed Ctrl+D to signal end of input
    return "\n".join(lines)


def read_prd(prd_path: str | None) -> str:
    """Read PRD from file or stdin.

    Args:
        prd_path: Path to PRD file, or None to read from stdin.

    Returns:
        PRD text content.
    """
    if prd_path is not None:
        path = Path(prd_path)
        if not path.is_file():
            print(f"Error: PRD file not found: {prd_path}")
            sys.exit(1)
        return path.read_text()

    print()
    print("Paste PRD (Ctrl+D or blank line to finish):")
    return read_multiline_input()


def collect_repos_from_storages(
    multi_ananta: Ananta, explorer_ananta: Ananta
) -> list[tuple[str, str | None, str]]:
    """Collect repos from both multi-repo and repo-explorer storages.

    Returns list of (project_id, source_url, storage_label) tuples.
    Multi-repo storage takes priority for deduplication.
    """
    repos: list[tuple[str, str | None, str]] = []
    seen_ids: set[str] = set()

    # Multi-repo storage first (takes priority)
    for project_id in multi_ananta.list_projects():
        info = multi_ananta.get_project_info(project_id)
        repos.append((project_id, info.source_url, "multi-repo"))
        seen_ids.add(project_id)

    # Repo-explorer storage (skip duplicates)
    for project_id in explorer_ananta.list_projects():
        if project_id in seen_ids:
            continue
        info = explorer_ananta.get_project_info(project_id)
        repos.append((project_id, info.source_url, "repo-explorer"))
        seen_ids.add(project_id)

    return repos


def show_multi_picker(
    repos: list[tuple[str, str | None, str]],
) -> list[tuple[str, str | None, str]]:
    """Show interactive multi-select picker for repos.

    All repos start selected. User enters numbers to toggle,
    'a' to add a URL, 'done' to proceed.

    Args:
        repos: List of (project_id, source_url, storage_label) tuples.

    Returns:
        Selected repos as list of (project_id, source_url, storage_label).
        For user-added URLs, project_id is the URL itself and storage_label is "new".
    """
    # Mutable selection state: index -> selected
    selected = {i: True for i in range(len(repos))}
    all_repos = list(repos)  # May grow if user adds URLs

    while True:
        # Display grouped by storage
        print()
        print("Available repositories:")
        storages: dict[str, list[tuple[int, str, str | None]]] = {}
        for i, (pid, url, label) in enumerate(all_repos):
            storages.setdefault(label, []).append((i, pid, url))

        num = 0
        index_map: dict[int, int] = {}  # display_num -> all_repos index
        for label in ["multi-repo", "repo-explorer", "new"]:
            if label not in storages:
                continue
            print(f"  [{label}]")
            for repo_idx, pid, url in storages[label]:
                num += 1
                index_map[num] = repo_idx
                marker = "*" if selected.get(repo_idx, True) else " "
                print(f"    {num}. [{marker}] {pid}")

        selected_count = sum(1 for s in selected.values() if s)
        print()
        print(f"Selected: {selected_count}/{len(all_repos)}")
        user_input = input("Toggle number, 'a' to add URL, 'done' to proceed: ").strip()

        if user_input.lower() == "done":
            chosen = [all_repos[i] for i, sel in selected.items() if sel]
            if not chosen:
                print("At least one repo must be selected.")
                continue
            return chosen

        if user_input.lower() == "a":
            url = input("Enter repo URL: ").strip()
            if url:
                idx = len(all_repos)
                all_repos.append((url, url, "new"))
                selected[idx] = True
            continue

        try:
            num_input = int(user_input)
            if num_input in index_map:
                repo_idx = index_map[num_input]
                selected[repo_idx] = not selected[repo_idx]
                action = "Selected" if selected[repo_idx] else "Deselected"
                print(f"  {action}: {all_repos[repo_idx][0]}")
            else:
                print(f"Invalid number: {num_input}")
        except ValueError:
            print(f"Unknown command: '{user_input}'")


def main() -> None:
    """Main entry point."""
    install_urllib3_cleanup_hook()
    args = parse_args()

    if not os.environ.get("ANANTA_API_KEY"):
        print("Error: ANANTA_API_KEY environment variable not set.")
        sys.exit(1)

    config = AnantaConfig.load(storage_path=STORAGE_PATH)
    ananta = Ananta(config=config)

    analyzer = MultiRepoAnalyzer(ananta)

    # Determine repos
    if args.repos:
        # Repos provided as CLI args
        repo_urls = args.repos
    else:
        # Interactive picker
        explorer_config = AnantaConfig.load(storage_path=EXPLORER_STORAGE_PATH)
        explorer_ananta = Ananta(config=explorer_config)
        available = collect_repos_from_storages(ananta, explorer_ananta)

        if not available:
            print("No repositories indexed yet.")
            url = input("Enter repo URL or local path: ").strip()
            if not url:
                print("No repository specified. Exiting.")
                sys.exit(0)
            repo_urls = [url]
        else:
            selected = show_multi_picker(available)
            repo_urls = [source_url or project_id for project_id, source_url, _label in selected]

    # Add repos
    for url in repo_urls:
        print(f"Adding: {url}")
        project_id = analyzer.add_repo(url)
        if project_id:
            print(f"  -> {project_id}")
        else:
            print("  Warning: Failed to add (will continue with other repos)")

    # Check if any repos were added successfully
    if not analyzer.repos:
        print("\nError: No repositories could be added.")
        if analyzer.failed_repos:
            print("Failed repos:")
            for url in analyzer.failed_repos:
                print(f"  - {url}")
        sys.exit(1)

    # Warn about partial failures
    if analyzer.failed_repos:
        failed = len(analyzer.failed_repos)
        succeeded = len(analyzer.repos)
        print(f"\nNote: {failed} repo(s) failed, continuing with {succeeded}.")

    # Get PRD
    prd = read_prd(args.prd)

    if not prd.strip():
        print("No PRD provided. Exiting.")
        sys.exit(0)

    # Callbacks
    def on_discovery(repo_hint: str) -> str | None:
        """Prompt user to provide URL for discovered dependency."""
        print(f"\nDiscovered dependency: {repo_hint}")
        response = input("Enter repo URL to add (or press Enter to skip): ").strip()
        return response if response else None

    def on_alignment_issue(report: AlignmentReport) -> str:
        print(f"\nAlignment score: {report.alignment_score:.0%}")
        if report.gaps:
            print(f"Gaps: {len(report.gaps)}")
            for gap in report.gaps[:3]:
                print(f"  - {gap}")
        if report.scope_creep:
            print(f"Scope creep: {len(report.scope_creep)}")
            for item in report.scope_creep[:3]:
                print(f"  - {item}")
        return input("Action (revise/accept/abort): ").strip().lower()

    def on_progress(phase: str, message: str) -> None:
        if args.verbose:
            print(f"[{phase}] {message}")

    # Run analysis
    print()
    print("Analyzing...")
    hld, alignment = analyzer.analyze(
        prd,
        on_discovery=on_discovery,
        on_alignment_issue=on_alignment_issue,
        on_progress=on_progress,
    )

    # Output
    print()
    print("=" * 60)
    print("DRAFT HIGH-LEVEL DESIGN")
    print("=" * 60)
    print()
    print(hld.raw_hld)

    print()
    print("=" * 60)
    print(f"ALIGNMENT: {alignment.alignment_score:.0%} coverage")
    print(f"Recommendation: {alignment.recommendation}")
    print("=" * 60)

    # Save option
    print()
    if input("Save to file? (y/n): ").lower() == "y":
        filename = input("Filename [hld-draft.md]: ").strip() or "hld-draft.md"
        Path(filename).write_text(hld.raw_hld)
        print(f"Saved to {filename}")


if __name__ == "__main__":
    main()
