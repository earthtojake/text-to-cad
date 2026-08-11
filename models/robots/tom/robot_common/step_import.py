from __future__ import annotations

from pathlib import Path

import build123d


def _compound_from_shapes(
    shapes: list[build123d.Shape],
    *,
    label: str = "",
) -> build123d.Compound:
    return build123d.Compound(obj=shapes, children=shapes, label=label)


def import_as_shape(step_path: Path) -> build123d.Shape:
    # Cache-backed import: reuses the inline __cadgen__ binary BREP so repeated
    # servo/part imports across rebuilds are ~tens of ms instead of a full re-parse.
    from cadgen.step_scene import import_step

    imported = import_step(step_path)
    solids = imported.solids()
    if solids:
        return _compound_from_shapes(solids)

    if isinstance(imported, build123d.Shape):
        return imported

    if not imported.children:
        raise RuntimeError(f"No CAD shapes found in {step_path}")
    return _compound_from_shapes(imported.children)
