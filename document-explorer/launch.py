#!/usr/bin/env python3
"""Launch the Ananta Document Explorer."""

import sys

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta Document Explorer",
    entry_point="ananta-document-explorer",
    frontend_dir="src/ananta/explorers/document/frontend",
    shared_frontend_dir="src/ananta/explorers/shared_ui/frontend",
)

if __name__ == "__main__":
    sys.exit(launch(config))
