"""Shared-instance assembly composition (public API).

``build123d.Shape.moved()`` deep-copies the entire shape graph per call
(``BRepBuilderAPI_Copy`` of every sub-shape), so placing N instances of a
heavy prototype costs N full copies at compose time plus N re-serializations
at content-hash time. ``compound_from_instances`` places each instance with an
OCCT location instead — O(1), sharing the prototype's underlying ``TShape`` —
and carries the assembly hierarchy (names, world placements) as an explicit
occurrence-metadata tree that the render packager consumes directly.

The returned compound can be a generator's whole ``gen_step`` shape or a child
nested anywhere inside a plain build123d compound tree: the packager splices
nested instance compounds into the descriptor walk, remapping occurrence ids
and accumulating world locations.
"""

from __future__ import annotations

from typing import Any, Sequence

from build123d import Compound, Location


def compound_from_instances(
    name: str,
    instances: Sequence[tuple[Any, Location, str]],
    *,
    assembly_mates: Sequence[dict[str, Any]] | None = None,
) -> Compound:
    """Bake ``(prototype, location, name)`` placements into one labeled compound.

    Every placement shares the prototype's geometry (no per-instance copy);
    ``location`` is the instance's placement relative to the returned compound.
    Prototype labels/colors on child shapes are preserved in the descriptor via
    the occurrence-metadata tree, which reads the UN-copied prototypes.
    """
    if not instances:
        raise RuntimeError(f"assembly {name!r} has no instances")
    from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound

    builder = TopoDS_Builder()
    occt_compound = TopoDS_Compound()
    builder.MakeCompound(occt_compound)
    occurrence_children: list[dict[str, Any]] = []
    for index, (prototype, location, instance_name) in enumerate(instances, start=1):
        builder.Add(occt_compound, prototype.wrapped.Moved(location.wrapped))
        occurrence_children.append(
            _occurrence_subtree(prototype, location, f"o1.{index}", str(instance_name))
        )
    compound = Compound(occt_compound, label=name)
    # Occurrence-metadata tree consumed by the render packager (see
    # cadgen._internal.component_package.build_package_from_compound); a plain
    # build123d compound has no such attribute and falls back to the child walk.
    compound._occurrence_tree = {"id": "o1", "name": name, "children": occurrence_children}
    if assembly_mates:
        compound.assembly_mates = [dict(mate) for mate in assembly_mates]
    return compound


def _occurrence_subtree(node: Any, parent_world_loc: Location, path: str, name: str) -> dict[str, Any]:
    """One occurrence-tree node, mirroring the packager's compound walk: leaves
    carry the local (un-copied) shape plus accumulated world location; a
    multi-part prototype becomes a subassembly grouping its leaves."""
    node_loc = getattr(node, "location", None)
    world_loc = (parent_world_loc * node_loc) if node_loc is not None else parent_world_loc
    child_shapes = list(getattr(node, "children", []) or [])
    if not child_shapes:
        return {
            "id": path,
            "name": name,
            "leaf": True,
            "shape": node,
            "world_loc": world_loc,
            "children": [],
        }
    children = [
        _occurrence_subtree(
            child,
            world_loc,
            f"{path}.{index}",
            str(getattr(child, "label", "") or f"{path}.{index}"),
        )
        for index, child in enumerate(child_shapes, start=1)
    ]
    return {"id": path, "name": name, "leaf": False, "children": children}
