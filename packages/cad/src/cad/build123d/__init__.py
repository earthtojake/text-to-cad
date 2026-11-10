"""``cad.build123d``: the build123d integration -- our helpers that take build123d's objects.

build123d (and the OCCT kernel under it, OCP) is the integration model code builds with. Its extra
is ``cad[build123d]``; its code runs in the process that calls it. This namespace holds only what WE
define for it, never build123d itself (``import build123d as bd`` stays build123d's): the producers
that make the document types from a build123d shape (``_producers``, registered in ``cad.registry``),
and the helpers a model calls with build123d objects:

* ``memo``: a function worth replaying on a later build (the engine's **Memo functions**);
* ``paint(shape, faces, material)``: a material or colour on some faces;
* what a part declares for a robot description, each a fact of the machine:
  ``frame(part, name, location)``, a named frame in its own frame (a robot description's sites),
  ``body(part, name=)``, a body of its own fixed to its link, ``limits(assembly, joint, effort=,
  velocity=)``, a joint's drive limits, ``mass(shape, grams)``, what a part or an assembly weighs in
  all, ``point_mass(part, grams, at, name=, inertia=)``, a lump its solids leave out, ``free(shape)``, a
  base not bolted to the world, and ``link(shape, name)``, the name of the link its parts make;
* the mechanism, as ISO 10303-242 (AP242) names its entities: ``mechanism_state``
  (``mechanism_state_representation``), ``configuration_sequence``
  (``interpolated_configuration_sequence``), ``gear_pair``, ``rack_and_pinion_pair``, ``screw_pair``,
  and ``posed(assembly, state)``, a copy of the assembly at a state;
* ``animation(assembly, name, duration=)``: a glTF animation, baked into each GLB the model declares;
* measurements of native geometry: ``closest_points``, ``overlap_volume``, ``is_sound``,
  ``topology_errors``, ``boundary_edges``, ``self_intersections``, ``mass_properties`` and their
  result types;
* flat patterns, exact 2D geometry from a solid's planar faces: ``flat_pattern``, ``planar_faces``,
  ``flatten_face``, ``flatten_faces``, ``union_faces``, ``offset_profile``;
* ``leaves(tree)``: every leaf of a tree (``step.read``'s, ``xbf.read``'s, a model's ``.shape``) placed where
  it stands, out of the tree, on the same B-rep: what ``located`` gives without copying the tree;
* the manufacturing check of exact geometry, a ``CheckResult`` with its findings at refs (``plate/face 7``):
  ``dfm(shape, process=...)`` -- what ``cad.step.dfm`` and ``cad.xbf.dfm`` run on a file's or a document's
  B-rep (``_dfm_check``; the measurements ``_dfm_brep`` and ``_dfm_<process>``) -- with ``cnc``,
  ``sheet_metal``, ``molding`` and ``printing`` its four processes by name;
  and ``unfold(shape, k_factor=)``, a bent sheet's flat pattern, its bends unrolled by their bend allowance;
* ``materials``, a submodule: named looks for what bd_materials' catalogue lacks (solder mask, ENIG,
  moulding compound, anodized, powder coat, ...), each a native ``bd_materials.FinishedMaterial``.

Every name loads on first use: ``import cad.build123d`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Each name and the module that defines it.
_NAMES = {
    "memo": "cad.engine.model",
    "paint": "cad.engine.model",
    "body": "cad.engine.declarations",
    "frame": "cad.engine.declarations",
    "free": "cad.engine.declarations",
    "limits": "cad.engine.declarations",
    "link": "cad.engine.declarations",
    "mass": "cad.engine.declarations",
    "point_mass": "cad.engine.declarations",
    "mechanism_state": "cad.engine.model",
    "configuration_sequence": "cad.engine.model",
    "animation": "cad.engine.model",
    "gear_pair": "cad.engine.mechanism",
    "rack_and_pinion_pair": "cad.engine.mechanism",
    "screw_pair": "cad.engine.mechanism",
    "posed": "cad.engine.mechanism",
    **{name: "cad.build123d._geometry" for name in (
        "GeometryError", "GeometryIssue", "ClosestPoints", "MassProperties", "closest_points", "overlap_volume",
        "is_sound", "topology_errors", "boundary_edges", "self_intersections", "mass_properties")},
    "leaves": "cad.build123d._leaves",
    **{name: "cad.build123d._flatten" for name in (
        "flat_pattern", "planar_faces", "flatten_face", "flatten_faces", "union_faces", "offset_profile")},
    **{name: "cad.build123d._dfm_check" for name in ("dfm", "cnc", "sheet_metal", "molding", "printing")},
    "unfold": "cad.build123d._dfm_sheet",
}

# Its public submodules, each imported on first use (``cad.build123d.materials``), offered with its names.
_SUBMODULES = ("materials",)

__all__ = sorted([*_NAMES, *_SUBMODULES])


def __getattr__(name: str) -> Any:
    import importlib

    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    module = _NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far, without loading any of them."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if TYPE_CHECKING:
    from cad.build123d import materials
    from cad.build123d._dfm_check import cnc, dfm, molding, printing, sheet_metal
    from cad.build123d._dfm_sheet import unfold
    from cad.build123d._flatten import (flat_pattern, flatten_face, flatten_faces, offset_profile, planar_faces,
                                        union_faces)
    from cad.build123d._geometry import (ClosestPoints, GeometryError, GeometryIssue, MassProperties,
                                         boundary_edges, closest_points, is_sound, mass_properties, overlap_volume,
                                         self_intersections, topology_errors)
    from cad.build123d._leaves import leaves
    from cad.engine.declarations import body, frame, free, limits, link, mass, point_mass
    from cad.engine.mechanism import gear_pair, posed, rack_and_pinion_pair, screw_pair
    from cad.engine.model import animation, configuration_sequence, mechanism_state, memo, paint
