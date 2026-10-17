"""A STEP snapshot's parts, as Python knows them: ``--mode list``, and what focus/hide keep.

``cadgen step snapshot --mode list`` answers here, from the tree and the store,
and never starts a browser. One row per placed occurrence (``#o:4b1f9e2a7c03``),
in the descriptor's order:

- ``ref`` and ``name`` are the occurrence's id and name exactly as
  :func:`cadgen.assembly_lookup.assembly_occurrence_rows` gives them -- the rows
  every selector, ``--focus`` and ``--hide`` resolve against, so a listed ref
  is one those accept;
- ``bounds`` is that row's box: the component's exact box (from its selector
  table), placed by the occurrence's transform, rounded to a nanometre;
- ``triangleCount`` and ``vertexCount`` are the part's stored display mesh's, as
  its record counts them (``cadgen.store.parts``): read, as the view the list is
  made from read it (``store.view.view_dir_for``).

A part whose mesh leaves out a face no mesher could cover is listed, drawn and
counted without it, and :func:`mesh_warnings` names the faces in the result's
warnings, for a list and a view alike -- as it names the faces a mesh draws off
their exact surface, which are drawn and counted as they are. A part no mesh could be made of at all is
left out of both, as the CAD Viewer leaves it out, and :func:`failed_part_warnings`
names it in the words a build uses (``#o:4b1f9e2a7c03 peg could not be meshed (...)``);
only a list or a view that would show nothing else fails (:func:`fail_if_nothing_left`).

``focus``/``hide`` select the same way the page's scene does for a view: an
occurrence matches a ref that IS its token, an ancestor group's token (the
tree says which leaves a group holds: ``groups``), or its name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = ["LIST_BOUNDS_DECIMALS", "fail_if_nothing_left", "failed_part_warnings", "failed_parts",
           "filter_occurrences", "list_rows", "mesh_warnings"]

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


def _matches(row: Mapping[str, Any], selector: str, groups: Mapping[str, Sequence[str]]) -> bool:
    occurrence_id = str(row.get("id") or "")
    if occurrence_id == selector or occurrence_id in (groups.get(selector) or ()):
        return True
    return str(row.get("name") or "") == selector


def filter_occurrences(
    rows: Sequence[Mapping[str, Any]], selection: Mapping[str, Any] | None,
    *, groups: Mapping[str, Sequence[str]] | None = None,
) -> list:
    """The rows ``selection``'s focus keeps and its hide does not remove. ``groups`` maps
    each tree node's token to the leaves beneath it (``assembly_lookup.assembly_group_members``),
    so a group ref keeps or removes its subtree.

    Raises ``ValueError`` when nothing is left: an empty picture is never the
    answer to a selection.
    """
    selection = selection if isinstance(selection, Mapping) else {}
    focus = _selector_values(selection.get("focus"))
    hide = _selector_values(selection.get("hide"))
    if not focus and not hide:
        return list(rows)
    groups = groups or {}
    kept = [
        row for row in rows
        if (not focus or any(_matches(row, selector, groups) for selector in focus))
        and not any(_matches(row, selector, groups) for selector in hide)
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


def _records(descriptor: Mapping[str, Any], cids) -> dict:
    """``{cid: record}`` of the stored parts of ``cids`` (``cadgen.store.parts``)."""
    from cadgen.store.parts import probe

    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}
    records = {}
    for cid in cids:
        key = str((components.get(cid) or {}).get("part") or "")
        record = probe(key) if key else None
        if record is not None:
            records[cid] = record
    return records


def has_surfaces(descriptor: Mapping[str, Any]) -> bool:
    """Whether any placed occurrence's part has a face to draw, by its selector table's
    face count. A model with none -- empty, or only curves and points -- is drawn as
    nothing, which nobody would guess from a blank image. A part the store does not
    hold is taken to have faces: this never claims an absence it did not see."""
    occurrences = descriptor.get("occurrences") if isinstance(descriptor.get("occurrences"), list) else []
    placed = list(dict.fromkeys(str(row.get("component") or "") for row in occurrences if isinstance(row, Mapping)))
    records = _records(descriptor, placed)
    return any(cid not in records or records[cid]["selectors"]["faceCount"] > 0 for cid in placed)


def mesh_warnings(
    descriptor: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    consequence: str,
) -> list[str]:
    """A warning per component whose stored display mesh leaves faces undrawn
    (``cadgen.store.meshes``): the faces no mesher could cover, with the occurrences of
    ``rows`` that place the component and ``consequence``. A probe per component when it
    names none."""
    from cadgen.store.meshes import placements, unmeshed_warning
    from cadgen.store.parts import stored_unmeshed_faces, unmeshed_face_names

    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}
    failed = failed_parts(descriptor)
    warnings = []
    for cid, occurrences in placements(rows).items():
        key = str((components.get(cid) or {}).get("part") or "")
        unmeshed = stored_unmeshed_faces(key) if key and cid not in failed else []
        if unmeshed:
            warnings.append(unmeshed_warning(occurrences, unmeshed_face_names(key, unmeshed), consequence))
    return warnings


def failed_parts(descriptor: Mapping[str, Any]) -> dict[str, str]:
    """``{cid: reason}``: the components the view left out, no mesh having been made of
    them (their ``failure``, ``cadgen.store.view.materialize_parts``)."""
    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}
    return {str(cid): str(entry["failure"]) for cid, entry in components.items()
            if isinstance(entry, Mapping) and entry.get("failure")}


def failed_part_warnings(
    descriptor: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    consequence: str,
) -> list[str]:
    """A warning per component of ``rows`` the view left out (:func:`failed_parts`), in the
    words a build says it in -- the occurrences of ``rows`` that place it and why
    (``#o:3f2a9c1d7e5b peg could not be meshed (...)``) -- and ``consequence``."""
    from cadgen.store.meshes import failed_part_warning, placements

    failed = failed_parts(descriptor)
    if not failed:
        return []
    return [failed_part_warning(occurrences, failed[cid], consequence)
            for cid, occurrences in placements(rows).items() if cid in failed]


def fail_if_nothing_left(descriptor: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    """Raise when the view left out every part ``rows`` place (:func:`failed_parts`): there
    is nothing to draw or list, and the failure is theirs -- the ``MeshProductionError``
    naming them (``cadgen.store.view.failed_parts_error``), as a view none of whose parts
    could be meshed fails."""
    from cadgen.store.meshes import placements

    failed = failed_parts(descriptor)
    placed = placements(rows)
    if failed and placed and all(cid in failed for cid in placed):
        from cadgen.store.view import failed_parts_error

        raise failed_parts_error({cid: failed[cid] for cid in placed}, placed)


def list_rows(
    descriptor: Mapping[str, Any],
    package_dir: Path,
    *,
    selection: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """The ``--mode list`` rows for a STEP tree (see the module docstring)."""
    from cadgen.assembly_lookup import assembly_group_members, assembly_occurrence_rows

    failed = failed_parts(descriptor)
    rows = [row for row in filter_occurrences(assembly_occurrence_rows(descriptor, package_dir), selection,
                                              groups=assembly_group_members(descriptor))
            if str(row.get("component") or "") not in failed]
    records = _records(descriptor, sorted({str(row["component"]) for row in rows if row.get("component")}))
    listed = []
    for row in rows:
        mesh = (records.get(str(row.get("component"))) or {}).get("glb") or {}
        triangles, vertices = int(mesh.get("indexCount") or 0) // 3, int(mesh.get("vertexCount") or 0)
        box = row.get("bbox") if isinstance(row.get("bbox"), Mapping) else None
        listed.append({
            "ref": f"#{row['id']}",
            "name": str(row.get("name") or row["id"]),
            "triangleCount": triangles,
            "vertexCount": vertices,
            "bounds": {"min": _rounded(box["min"]), "max": _rounded(box["max"])} if box else None,
        })
    return listed
