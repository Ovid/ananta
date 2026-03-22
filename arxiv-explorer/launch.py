#!/usr/bin/env python3
"""Launch the Ananta arXiv Web Explorer."""

import sys

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta arXiv Web Explorer",
    entry_point="ananta-web",
    frontend_dir="src/ananta/explorers/arxiv/frontend",
)

if __name__ == "__main__":
    sys.exit(launch(config))
