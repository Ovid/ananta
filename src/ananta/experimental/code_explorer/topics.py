"""Topic management for the code explorer.

Thin subclass of ``BaseTopicManager`` — all logic lives in the base class.
Kept as a separate class so type annotations in ``CodeExplorerState``
remain specific to this explorer.
"""

from __future__ import annotations

from shesha.experimental.shared.topics import BaseTopicManager, _slugify

__all__ = ["CodeExplorerTopicManager", "_slugify"]


class CodeExplorerTopicManager(BaseTopicManager):
    pass
