"""Persistent conversation session for the arxiv web interface.

Thin wrapper around the shared ``WebConversationSession`` that overrides the
conversation file name to ``_conversation.json`` for backward compatibility
with existing arxiv explorer data.
"""

from __future__ import annotations

from pathlib import Path

from ananta.explorers.shared_ui.session import WebConversationSession as _SharedSession

CONVERSATION_FILE = "_conversation.json"


class WebConversationSession(_SharedSession):
    """Arxiv-flavoured conversation session.

    Identical to the shared session except it persists to
    ``_conversation.json`` (legacy arxiv format) instead of
    ``conversation.json``.
    """

    def __init__(self, project_dir: Path) -> None:
        super().__init__(project_dir, conversation_file=CONVERSATION_FILE)
