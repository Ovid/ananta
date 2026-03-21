"""Entry point for ananta-web."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from ananta.experimental.web.api import create_api
from ananta.experimental.web.dependencies import create_app_state


def main() -> None:
    """Run the Ananta arXiv Web Explorer."""
    parser = argparse.ArgumentParser(description="Ananta arXiv Web Explorer")
    parser.add_argument("--model", type=str, help="LLM model to use")
    parser.add_argument("--data-dir", type=str, help="Data directory")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--open", action="store_true", help="Open browser on startup")
    parser.add_argument("--bind", type=str, default="127.0.0.1", help="Bind address")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    state = create_app_state(data_dir=data_dir, model=args.model)
    app = create_api(state)

    url = f"http://{args.bind}:{args.port}"
    print(f"\n  Ananta arXiv Explorer → {url}\n")

    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.bind, port=args.port)


if __name__ == "__main__":
    main()
