"""Topic management for the document explorer.

Thin subclass of ``BaseTopicManager`` — all logic lives in the base class.
Kept as a separate class so type annotations in ``DocumentExplorerState``
remain specific to this explorer.
"""

from __future__ import annotations

from ananta.explorers.shared_ui.topics import BaseTopicManager, _slugify

__all__ = ["DocumentTopicManager", "_slugify"]


class DocumentTopicManager(BaseTopicManager):
    pass
