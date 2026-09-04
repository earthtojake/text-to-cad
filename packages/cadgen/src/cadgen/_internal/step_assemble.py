"""STEP assembly from a tree's exact-shape component objects.

The tree is the document of record (design/step-document-architecture.md):
``components/<cid>.brep`` holds each part's exact geometry and the
assembly.json holds the tree, placements, labels, colors, and mates. Writing
the STEP file is therefore a pure ASSEMBLY step — read blobs once, place
occurrences (sharing each component's TShape, exactly like the original
build did), rebuild the nested compound from the assembly.json's assembly
tree, and hand the result to the existing XCAF writer. A ``@step`` entry never
runs here; this is the FreeCAD save path, not a recompute.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.component_package import (
    COMPONENT_DIRNAME,
    read_package_descriptor,
)


def _location_from_matrix(matrix: list[float]):
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf
    from build123d import Location

    trsf = gp_Trsf()
    if isinstance(matrix, (list, tuple)) and len(matrix) >= 12:
        trsf.SetValues(*[float(v) for v in matrix[:12]])
    return Location(TopLoc_Location(trsf))


def _load_component_shapes(package_dir: Path, descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Each unique component's exact shape, BinTools-read ONCE per cid.
    Occurrences share the TShape through ``moved()``, matching how the
    original build deduped repeats."""
    from cadgen._internal.component_package import _build123d_shape_from_brep_bytes

    shapes: dict[str, Any] = {}
    for cid, entry in (descriptor.get("components") or {}).items():
        ref = str(entry.get("brep") or f"{COMPONENT_DIRNAME}/{cid}.brep")
        blob_path = package_dir / ref
        shapes[cid] = _build123d_shape_from_brep_bytes(blob_path.read_bytes())
    return shapes


def _color_from_entry(entry: Mapping[str, Any]):
    values = entry.get("color")
    if not isinstance(values, (list, tuple)) or len(values) < 3:
        return None
    try:
        from build123d import Color

        return Color(*[float(v) for v in values[:4]])
    except Exception:
        return None


def assemble_compound_from_package(package_dir: Path):
    """Reconstruct the model compound (placed occurrences, labels, colors,
    nested assembly grouping, mates) purely from the tree."""
    from build123d import Compound

    descriptor = read_package_descriptor(package_dir)
    if descriptor is None:
        raise FileNotFoundError(f"no assembly.json (materialized tree) under {package_dir}")
    shapes = _load_component_shapes(package_dir, descriptor)
    components = descriptor.get("components") or {}

    placed_by_id: dict[str, Any] = {}
    for occurrence in descriptor.get("occurrences") or []:
        cid = str(occurrence.get("component") or "")
        base = shapes.get(cid)
        if base is None:
            raise FileNotFoundError(
                f"package {package_dir} is missing component blob {cid}")
        child = base.moved(_location_from_matrix(occurrence.get("transform")))
        child.label = str(occurrence.get("name") or occurrence.get("id") or "")
        # Occurrence color first: generators author per-occurrence colors and
        # the assembly.json records them there; the component entry's color is the
        # shared-part fallback. Reading only the component entry silently wrote
        # colorless STEP files for every model whose colors were per-occurrence
        # (the planetary pilot), which then imported colorless everywhere.
        color = _color_from_entry(occurrence) or _color_from_entry(components.get(cid) or {})
        if color is not None:
            child.color = color
        placed_by_id[str(occurrence.get("id") or "")] = child

    # Nested grouping: transforms are ABSOLUTE, so group nodes are plain
    # Compounds at identity carrying only structure + names for the XCAF
    # product tree. Fall back to a flat compound when the assembly.json
    # predates the assembly tree.
    def _build_node(node: Mapping[str, Any]):
        node_type = str(node.get("nodeType") or "")
        node_id = str(node.get("id") or "")
        if node_type == "part" or (not node.get("children") and node_id in placed_by_id):
            return placed_by_id.get(node_id)
        children = [
            built
            for child in node.get("children") or []
            if (built := _build_node(child)) is not None
        ]
        if not children:
            return None
        group = Compound(children=children)
        group.label = str(node.get("name") or node_id)
        return group

    root_node = (descriptor.get("assembly") or {}).get("root")
    compound = _build_node(root_node) if isinstance(root_node, Mapping) else None
    if compound is None:
        children = [child for child in placed_by_id.values()]
        if len(children) == 1:
            compound = children[0]
        else:
            compound = Compound(children=children)
    compound.label = str(descriptor.get("rootName") or getattr(compound, "label", "") or "model")
    # No mates here: they are source-derived and live in the model-side
    # sidecar, which a tree (keyed by content, model-blind) cannot name.
    # Scene loads attach them from the sidecar (step_scene_package); the one
    # write-path caller assembles STEP bytes, which never carry mates.
    return compound, descriptor


def assemble_step_from_package(
    package_dir: Path,
    step_path: Path,
    *,
    logger: Any | None = None,
) -> str:
    """Write ``step_path`` from the tree. Returns the written file's hash
    (the same value the export record and the render-side freshness gate
    key on)."""
    from cadgen.step_export import export_build123d_step_file

    compound, _descriptor = assemble_compound_from_package(package_dir)
    return export_build123d_step_file(compound, step_path, logger=logger)
