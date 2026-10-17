"""Saved documents, for tests.

A build's saved document is its result, the tree its STEP was exported from
(``cadgen.store.exports``): :func:`save_step` saves one as a model's build does. A cold
compile of the same bytes reads every component from the file; ``assert_same_document``
holds the two to everything they share, the colours as drawn."""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any, Mapping


def save_step(shape: Any, path: Path, *, root_name: str, force: bool = False, names: bool = True,
              namer: Any = None, materials: object = None) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    """Save ``shape`` to ``path`` as a model's build saves its STEP
    (``_internal/generation.py``): its result tree published
    (``store.build.build_tree_from_compound``), the STEP exported from that tree in this
    process (``store.exports.export_step``; ``names`` False writes it plain), its bytes
    mapped to the tree pending their verify, then the verify
    (``store.exports.verify_document``). Returns ``(tree_hash, tree, stats, sha256)``;
    ``stats`` carries the export's answer (``export``) and the verify's (``verify``)."""
    from cadgen.store.build import build_tree_from_compound
    from cadgen.store.exports import export_step, verify_document
    from cadgen.store.parts import producer_identity
    from cadgen.store.records import note_document_tree

    live: dict[str, Any] = {}
    tree_hash, tree, stats = build_tree_from_compound(shape, root_name=root_name, force=force, namer=namer,
                                                     materials=materials, live=live)
    export = export_step(tree_hash, Path(path), names=names, shapes=live)
    try:
        producer = producer_identity()
    except ValueError:
        producer = None
    note_document_tree(export["sha256"], tree_hash, producer=producer, verified=False, plain=not names)
    verify = verify_document(tree_hash, Path(path), export["sha256"], producer=export["producer"])
    return tree_hash, tree, {**stats, "export": export, "verify": verify}, str(export["sha256"])


def _occurrences(tree: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """A tree's occurrences by token: the order a tree lists them in is not its document's
    (a flattened tree lists a parent's own before its links'), its structure is."""
    return sorted(tree.get("occurrences") or [], key=lambda occurrence: str(occurrence["id"]))


def document_shape(tree: Mapping[str, Any]) -> dict[str, Any]:
    """``tree`` (a document tree, or one flattened) as a reader of its file sees it: its
    label, units, kind, structure and occurrences by token, each occurrence's component
    replaced by its kind, its colours to the single precision a STEP reader keeps -- no
    placements, bounds or face colours (compare those with a tolerance:
    :func:`assert_same_document`). What a tree carries beside its document -- its links,
    stats, edge capabilities and finishes -- is not read, and neither is which occurrences
    share a component: a parse shares one prototype among products of equal geometry, a
    build keeps the components it made."""
    components = tree.get("components") or {}
    occurrences = []
    for occurrence in _occurrences(tree):
        entry = components.get(str(occurrence.get("component") or "")) or {}
        shaped = {key: value for key, value in occurrence.items() if key not in ("transform", "color")}
        shaped["component"] = entry.get("kind")
        if occurrence.get("color") is not None:
            # A STEP reader keeps a colour to single precision.
            shaped["color"] = [struct.unpack("f", struct.pack("f", float(channel)))[0]
                               for channel in occurrence["color"]]
        occurrences.append(shaped)
    shape = {key: tree.get(key) for key in ("label", "units", "entryKind", "assembly")}
    shape["occurrences"] = occurrences
    return shape


def face_colors(tree: Mapping[str, Any]) -> list[tuple[dict[str, list[float]], Any]]:
    """Each occurrence's component's face colours, by ordinal as text, and the
    occurrence's colour, occurrence by occurrence in token order."""
    components = tree.get("components") or {}
    return [({str(ordinal): color for ordinal, color in
              ((components.get(str(occurrence.get("component") or "")) or {}).get("faceColors") or {}).items()},
             occurrence.get("color"))
            for occurrence in _occurrences(tree)]


def assert_same_document(test: Any, warm: Mapping[str, Any], cold: Mapping[str, Any], *, places: float = 1e-6) -> None:
    """A build's document tree ``warm`` and a cold compile ``cold`` of the bytes it wrote
    describe one document: the same structure and appearance, components alike occurrence
    by occurrence, placed alike to the precision a STEP file states a real with, drawn in
    the same colours face by face to the single precision a STEP reader keeps -- the same
    face colours, or, where the build's leaf is the occurrence it was written from,
    coloured as a whole, the compile's every face in that colour (a reader returns a
    placement's colour on its faces) -- and bounds within ``places``."""
    test.assertEqual(document_shape(warm), document_shape(cold))
    for built, read in zip(_occurrences(warm), _occurrences(cold)):
        test.assertTrue(all(math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
                            for a, b in zip(built["transform"], read["transform"])),
                        f"{built['id']}: placed at {built['transform']}, read at {read['transform']}")
    for (built, placed), (read, _read_placed) in zip(face_colors(warm), face_colors(cold)):
        if not built and read and placed is not None:
            for ordinal, color in read.items():
                test.assertTrue(all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(color, placed)),
                                f"face {ordinal}: {color} is not the occurrence's {placed}")
            continue
        test.assertEqual(sorted(built), sorted(read))
        for ordinal, color in built.items():
            for a, b in zip(color, read[ordinal]):
                test.assertTrue(math.isclose(a, b, abs_tol=1e-6), f"face {ordinal}: {color} != {read}")
    for side in ("min", "max"):
        for built, read in zip((warm.get("bbox") or {}).get(side) or [], (cold.get("bbox") or {}).get(side) or []):
            test.assertTrue(math.isclose(built, read, abs_tol=places), f"bbox {side}: {built} != {read}")
