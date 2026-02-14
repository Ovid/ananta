"""Code Explorer entry point."""

from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the code explorer."""
    parser = argparse.ArgumentParser(description="Shesha Code Explorer")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    return parser.parse_args(argv)


def main() -> None:
    """Launch the code explorer."""
    args = parse_args()
    print(f"Code Explorer would start on port {args.port}")


if __name__ == "__main__":
    main()
