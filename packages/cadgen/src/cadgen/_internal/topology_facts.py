"""A component's topology facts as an object, read without the kernel.

``topology_extract.extract_topology_facts`` reads a component's topology facts
off its BREP with OCCT, and the selector table is built from them
(``selector_table``). They are a plain JSON structure -- three ordinal tables,
``shapes``, ``faces`` and ``edges`` -- and nothing stores them but an
eager-only component's tree, which pins them as an object in the component's
geometry identity (``component_package``). Their bytes and their check live
here, so a process that only reads -- the build pool verifying a tree's
closure, the viewer pinning a tree -- never loads OCCT.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["TABLES", "check_topology_facts", "read_topology_facts", "topology_facts_bytes"]

TABLES = ("shapes", "faces", "edges")


def check_topology_facts(facts: Any) -> dict:
    """``facts`` when it is the three whole ordinal tables; ``ValueError`` for anything else."""
    if type(facts) is not dict or set(facts) != set(TABLES):
        raise ValueError("invalid topology facts")
    for name in TABLES:
        rows = facts[name]
        if (type(rows) is not list or any(type(row) is not dict for row in rows)
                or [row.get("ord") for row in rows] != list(range(1, len(rows) + 1))):
            raise ValueError(f"invalid topology facts {name} table")
    return facts


def topology_facts_bytes(facts: dict) -> bytes:
    """The facts as an eager-only component's tree pins them: compact JSON in the
    extractor's order, no NaN -- the form the selector table object takes too."""
    return json.dumps(check_topology_facts(facts), separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_topology_facts(payload: bytes) -> dict:
    """A pinned object's topology facts, checked; ``ValueError`` for anything else."""
    try:
        facts = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid topology facts JSON") from error
    return check_topology_facts(facts)
