"""The tape: an implicit part saved as data beside its mesh.

A field is an expression tree, and the tree is JSON. Written next to the
mesh a part produced (``<stem>.implicit.json``), it lets a saved part be
re-meshed at another resolution, probed for a distance, or measured
without its source -- the same independence a STEP has from the script
that wrote it. A tape holds the tree, the bounds, the resolution the mesh
was written at and the leaf table (id, kind, label, site) the mesh's nodes
refer to.

A part built from a :class:`~cadgen._internal.implicit.field.Custom` field
carries a Python function and cannot be taped; the authoring path skips
the tape and says so. A :class:`~cadgen._internal.implicit.field.Brep` leaf
is taped as the STEP it was read from (a path relative to the tape), so the
STEP must stay beside the tape.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cadgen._internal.implicit.field import Brep, Custom, Field, from_dict, leaves

__all__ = ["TAPE_SUFFIX", "TAPE_VERSION", "is_tapeable", "tape_path_for", "write_tape", "read_tape"]

TAPE_SUFFIX = ".implicit.json"
TAPE_VERSION = 1


def is_tapeable(field: Field) -> bool:
    return not any(isinstance(leaf, Custom) or (isinstance(leaf, Brep) and leaf.source is None) for leaf in leaves(field))


def tape_path_for(mesh_path: Path) -> Path:
    """``GLB/part.glb`` -> ``GLB/part.implicit.json``."""
    mesh_path = Path(mesh_path)
    return mesh_path.with_name(mesh_path.stem + TAPE_SUFFIX)


def leaf_table(field: Field) -> list[dict]:
    return [
        {"id": index, "kind": leaf.kind, "label": leaf.label or "", "site": leaf.site or ""}
        for index, leaf in enumerate(leaves(field))
    ]


def write_tape(field: Field, path: Path, *, name: str, resolution: float | None, units: str = "mm") -> Path:
    if not is_tapeable(field):
        raise ValueError("a field with a custom leaf, or a B-rep leaf with no file, cannot be written to a tape")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": "cadgen-implicit-tape",
        "version": TAPE_VERSION,
        "name": name,
        "units": units,
        "resolution": resolution,
        "bounds": field.bounds.to_dict(),
        "leaves": leaf_table(field),
        "field": _relative_sources(field.to_dict(), path.parent),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(document, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def _relative_sources(node: dict, base: Path) -> dict:
    """A brep leaf's STEP, written relative to the tape so the pair moves together."""
    if node.get("kind") == "brep" and node.get("source"):
        node = {**node, "source": os.path.relpath(node["source"], base)}
    for key in ("child", "operands"):
        if key in node:
            node = {**node, key: [_relative_sources(o, base) for o in node[key]] if key == "operands" else _relative_sources(node[key], base)}
    return node


def read_tape(path: Path) -> tuple[Field, dict]:
    """The field and the tape's header (name, units, resolution, bounds, leaves)."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not a tape: {error}") from None
    if not isinstance(document, dict) or document.get("format") != "cadgen-implicit-tape":
        raise ValueError(f"{path} is not a cadgen implicit tape (no 'format: cadgen-implicit-tape')")
    version = document.get("version")
    if version != TAPE_VERSION:
        raise ValueError(f"{path} is tape version {version!r}; this cadgen reads version {TAPE_VERSION}")
    field = from_dict(document["field"], base_dir=path.parent)
    header = {k: v for k, v in document.items() if k != "field"}
    return field, header
