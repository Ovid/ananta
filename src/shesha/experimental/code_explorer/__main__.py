"""Code Explorer entry point."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from shesha.experimental.code_explorer.api import create_api
from shesha.experimental.code_explorer.dependencies import create_app_state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the code explorer."""
    parser = argparse.ArgumentParser(description="Shesha Code Explorer")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--bind", type=str, default="127.0.0.1")
    return parser.parse_args(argv)


def main() -> None:
    """Launch the code explorer."""
    args = parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    state = create_app_state(data_dir=data_dir, model=args.model)
    app = create_api(state)

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    uvicorn.run(app, host=args.bind, port=args.port)


if __name__ == "__main__":
    main()
