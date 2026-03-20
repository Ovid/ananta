"""Interactive migration script for Shesha → Ananta directory renames.

Usage: python -m ananta.migrate
"""

from pathlib import Path


def get_migration_pairs() -> list[tuple[Path, Path]]:
    """Return all known (legacy, new) directory pairs."""
    home = Path.home()
    cwd = Path.cwd()
    return [
        (cwd / "shesha_data", cwd / "ananta_data"),
        (home / ".shesha-arxiv", home / ".ananta-arxiv"),
        (home / ".shesha" / "code-explorer", home / ".ananta" / "code-explorer"),
        (home / ".shesha" / "document-explorer", home / ".ananta" / "document-explorer"),
    ]


def find_legacy_directories(
    pairs: list[tuple[Path, Path]],
) -> list[tuple[Path, Path]]:
    """Return pairs where the legacy dir exists and the new one does not."""
    return [(old, new) for old, new in pairs if old.exists() and not new.exists()]


def perform_migration(to_migrate: list[tuple[Path, Path]]) -> None:
    """Rename legacy directories to their new paths."""
    for old, new in to_migrate:
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        print(f"  ✓ {old} → {new}")


def main() -> None:
    """Run the interactive migration."""
    pairs = get_migration_pairs()
    to_migrate = find_legacy_directories(pairs)

    if not to_migrate:
        print("Nothing to migrate. You're all set!")
        return

    print("Found legacy Shesha directories:\n")
    for old, new in to_migrate:
        print(f"  {old} → {new}")

    print()
    answer = input("Rename these directories? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    print()
    perform_migration(to_migrate)

    print("\n--- Manual steps remaining ---\n")
    print("1. Rename SHESHA_* environment variables to ANANTA_* in your shell config")
    print("   (e.g., SHESHA_API_KEY → ANANTA_API_KEY, SHESHA_MODEL → ANANTA_MODEL)\n")
    print("2. Rebuild the sandbox Docker image:")
    print("   docker build -t ananta-sandbox src/ananta/sandbox/\n")
    print("3. Update any .env files (SHESHA_* → ANANTA_*)\n")
    print("Done!")


if __name__ == "__main__":
    main()
