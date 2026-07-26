#!/usr/bin/env python3
"""Launch the Ananta Code Explorer."""

import sys

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta Code Explorer",
    entry_point="ananta-code",
    frontend_dir="src/ananta/explorers/code/frontend",
    requires_git=True,
    shared_frontend_dir="src/ananta/explorers/shared_ui/frontend",
)

if __name__ == "__main__":
    sys.exit(launch(config))
