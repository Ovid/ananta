"""CLI for validating prompt files.

Usage:
    python -m ananta.prompts [--prompts-dir /path/to/prompts]
"""

import argparse
import sys
from pathlib import Path

from ananta.prompts.loader import resolve_prompts_dir
from ananta.prompts.validator import PROMPT_SCHEMAS, PromptValidationError, validate_prompt


def main() -> int:
    """Validate prompt files and report results."""
    parser = argparse.ArgumentParser(
        description="Validate Ananta prompt files",
        prog="python -m ananta.prompts",
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=None,
        help="Directory containing prompt files (default: ANANTA_PROMPTS_DIR or bundled)",
    )
    args = parser.parse_args()

    prompts_dir = resolve_prompts_dir(args.prompts_dir)
    print(f"Validating prompts in {prompts_dir}...")

    errors: list[str] = []
    for filename in sorted(PROMPT_SCHEMAS.keys()):
        schema = PROMPT_SCHEMAS[filename]
        filepath = prompts_dir / filename
        if not filepath.exists():
            if schema.required_file:
                errors.append(f"✗ {filename} - File not found")
            else:
                print(f"- {filename} - Skipped (optional)")
            continue

        try:
            content = filepath.read_text()
            validate_prompt(filename, content)
            print(f"✓ {filename} - OK")
        except PromptValidationError as e:
            errors.append(f"✗ {filename} - {e}")

    if errors:
        print()
        for error in errors:
            print(error)
        print(f"\nValidation failed: {len(errors)} error(s)")
        return 1

    print(f"\nValidation passed: {len(PROMPT_SCHEMAS)} file(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
