"""Stable identities for KiCad items.

Every KiCad item carries a UUID, and the schematic and the board refer to each
other through them (a footprint's ``path`` is its symbol's UUID). cadgen's
writers derive each one from a name for the item -- ``symbol:U1:2``,
``footprint:R3:pad:1`` -- so the same board always gets the same UUIDs, the
documents are a pure function of the script's result, and a rebuilt board
diffs cleanly against the last one.
"""

from __future__ import annotations

import uuid

__all__ = ["Ids"]

_ROOT = uuid.uuid5(uuid.NAMESPACE_URL, "https://texttocad.dev/cadgen/kicad")


class Ids:
    """The UUIDs of one document's items, keyed by a name for each item.

    Calling issues an item's UUID, once per document; :meth:`of` names another
    item's UUID without issuing it (a board footprint pointing at its symbol).
    Two documents of one project share the namespace, so the board and the
    schematic agree on every UUID they both mention.
    """

    def __init__(self, project: str):
        self._namespace = uuid.uuid5(_ROOT, str(project))
        self._issued: set[str] = set()

    def of(self, key: str) -> str:
        return str(uuid.uuid5(self._namespace, key))

    def __call__(self, key: str) -> str:
        value = self.of(key)
        if value in self._issued:
            raise ValueError(f"two items asked for the identity {key!r}")
        self._issued.add(value)
        return value
