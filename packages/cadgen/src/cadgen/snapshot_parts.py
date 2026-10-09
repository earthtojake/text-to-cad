"""A STEP snapshot's parts, as Python knows them: ``--mode list``, and what focus/hide keep.

``cadgen step snapshot --mode list`` answers here, from the tree and the store,
and never starts a browser. One row per placed occurrence (``#o1.2``), in the
descriptor's order:

- ``ref`` and ``name`` are the occurrence's id and name exactly as
  :func:`cadgen.assembly_lookup.assembly_occurrence_rows` gives them -- the rows
  every selector, ``--focus`` and ``--hide`` resolve against, so a listed ref
  is one those accept;
- ``bounds`` is that row's box: the component's exact box (from its SURF),
  placed by the occurrence's transform, rounded to a nanometre;
- ``triangleCount`` and ``vertexCount`` are the stored display mesh's
  (``cadgen.store.meshes``) at the tessellation a view of the same job would
  draw (``cadgen.tessellation_policy.snapshot_tessellation``), meshed in the
  build pool when the store has none.

``focus``/``hide`` select the same way the page's scene does for a view: an
occurrence matches a ref that IS its id, an ancestor group's id (``o1.2``
covers ``o1.2.3``), or its name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = ["LIST_BOUNDS_DECIMALS", "filter_occurrences", "list_rows"]

# Three decimals of a millimetre is a nanometre: far below any tolerance a model
# is built to, and a fifth of the payload full float64 noise would be.
LIST_BOUNDS_DECIMALS = 3


def _selector_values(value: object) -> list[str]:
    values = value if isinstance(value, list) else str(value or "").split(",")
    out = []
    for item in values:
        text = str(item or "").strip()
        text = text[1:] if text.startswith("#") else text
        out.extend(part.strip() for part in text.split(",") if part.strip())
    return out


def _matches(row: Mapping[str, Any], selector: str) -> bool:
    occurrence_id = str(row.get("id") or "")
    if occurrence_id == selector or occurrence_id.startswith(f"{selector}."):
        return True
    return str(row.get("name") or "") == selector


def filter_occurrences(rows: Sequence[Mapping[str, Any]], selection: Mapping[str, Any] | None) -> list:
    """The rows ``selection``'s focus keeps and its hide does not remove.

    Raises ``ValueError`` when nothing is left: an empty picture is never the
    answer to a selection.
    """
    selection = selection if isinstance(selection, Mapping) else {}
    focus = _selector_values(selection.get("focus"))
    hide = _selector_values(selection.get("hide"))
    if not focus and not hide:
        return list(rows)
    kept = [
        row for row in rows
        if (not focus or any(_matches(row, selector) for selector in focus))
        and not any(_matches(row, selector) for selector in hide)
    ]
    if not kept:
        raise ValueError("No renderable parts remain after applying focus/hide filters")
    return kept


def _rounded(values: Sequence[float]) -> list:
    out = []
    for value in values:
        number = round(float(value), LIST_BOUNDS_DECIMALS)
        out.append(0 if number == 0 else (int(number) if number == int(number) else number))
    return out


def _mesh_counts(descriptor: Mapping[str, Any], cids: set[str], tessellation: Mapping[str, float]) -> dict:
    """``{cid: (triangles, vertices)}`` from the stored meshes at ``tessellation``."""
    from cadgen.store.meshes import tessellation_key
    from cadgen.store.tess_cache import produce_meshes

    chord = float(tessellation["chordTolerance"])
    angle = float(tessellation["angleTolerance"])
    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}
    keys = {}
    for cid in sorted(cids):
        surface_input = str((components.get(cid) or {}).get("surfaceInput") or "")
        if surface_input:
            keys[cid] = tessellation_key(surface_input, chord, angle)
    records = produce_meshes(list(keys.values())) if keys else {}
    counts = {}
    for cid, key in keys.items():
        record = records.get(key)
        if isinstance(record, Mapping):
            counts[cid] = (int(record["indexCount"]) // 3, int(record["vertexCount"]))
    return counts


def has_surfaces(descriptor: Mapping[str, Any], package_dir: Path) -> bool:
    """Whether any placed occurrence's component has a face to draw, by its SURF's
    face count. A model with none -- empty, or only curves and points -- is drawn as
    nothing, which nobody would guess from a blank image. A SURF that does not read
    is taken to have faces: this never claims an absence it did not see."""
    from cadgen._internal.surf_container import read_surf_index

    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}
    occurrences = descriptor.get("occurrences") if isinstance(descriptor.get("occurrences"), list) else []
    placed = dict.fromkeys(str(row.get("component") or "") for row in occurrences if isinstance(row, Mapping))
    for cid in placed:
        surf = str((components.get(cid) or {}).get("surf") or "")
        try:
            counts = read_surf_index(package_dir / surf).get("counts") if surf else None
        except (OSError, ValueError):
            return True
        if not isinstance(counts, Mapping) or int(counts.get("faces") or 0) > 0:
            return True
    return False


def list_rows(
    descriptor: Mapping[str, Any],
    package_dir: Path,
    *,
    selection: Mapping[str, Any] | None,
    tessellation: Mapping[str, float],
) -> list[dict[str, Any]]:
    """The ``--mode list`` rows for a STEP tree (see the module docstring)."""
    from cadgen.assembly_lookup import assembly_occurrence_rows

    rows = filter_occurrences(assembly_occurrence_rows(descriptor, package_dir), selection)
    counts = _mesh_counts(descriptor, {str(row["component"]) for row in rows if row.get("component")}, tessellation)
    listed = []
    for row in rows:
        triangles, vertices = counts.get(str(row.get("component")), (0, 0))
        box = row.get("bbox") if isinstance(row.get("bbox"), Mapping) else None
        listed.append({
            "ref": f"#{row['id']}",
            "name": str(row.get("name") or row["id"]),
            "triangleCount": triangles,
            "vertexCount": vertices,
            "bounds": {"min": _rounded(box["min"]), "max": _rounded(box["max"])} if box else None,
        })
    return listed
