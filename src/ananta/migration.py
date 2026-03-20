"""Legacy directory migration checks for the Shesha -> Ananta rename."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def check_legacy_directory(
    legacy_path: Path,
    new_path: Path,
    legacy_name: str,
    new_name: str,
) -> None:
    """Warn if a legacy Shesha directory exists and the new one does not."""
    if legacy_path.exists() and not new_path.exists():
        logger.warning(
            "Found legacy directory '%s' at %s. "
            "Ananta now uses '%s'. Please rename it:\n"
            "  mv %s %s",
            legacy_name,
            legacy_path,
            new_name,
            legacy_path,
            legacy_path.parent / new_name,
        )
