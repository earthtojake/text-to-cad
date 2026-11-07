"""``cad.build123d``: the build123d integration -- our helpers that take build123d's objects.

build123d (and the OCCT kernel under it, OCP) is the integration model code builds with. Its extra
is ``cad[build123d]``; its code runs in the process that calls it. This namespace holds only what WE
define for it, never build123d itself (``import build123d as bd`` stays build123d's): the producers
that make the document types from a build123d shape (``_producers``, registered in ``cad.registry``),
and the helpers a model calls with build123d objects:

* ``memo``: a function worth replaying on a later build (the engine's **Memo functions**);
* ``paint(shape, faces, material)``: a material or colour on some faces;
* the mechanism, as ISO 10303-242 (AP242) names its entities: ``mechanism_state``
  (``mechanism_state_representation``), ``configuration_sequence``
  (``interpolated_configuration_sequence``), ``gear_pair``, ``rack_and_pinion_pair``, ``screw_pair``,
  and ``posed(assembly, state)``, a copy of the assembly at a state;
* ``animation(assembly, name, duration=)``: a glTF animation, baked into each GLB the model declares;
* measurements of native geometry: ``closest_points``, ``overlap_volume``, ``is_sound``,
  ``topology_errors``, ``boundary_edges``, ``self_intersections``, ``mass_properties`` and their
  result types;
* flat patterns, exact 2D geometry from a solid's planar faces: ``flat_pattern``, ``planar_faces``,
  ``flatten_face``, ``flatten_faces``, ``union_faces``, ``offset_profile``.

Every name loads on first use: ``import cad.build123d`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Each name and the module that defines it.
_NAMES = {
    "memo": "cad.engine.model",
    "paint": "cad.engine.model",
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
    **{name: "cad.build123d._flatten" for name in (
        "flat_pattern", "planar_faces", "flatten_face", "flatten_faces", "union_faces", "offset_profile")},
}

__all__ = sorted(_NAMES)


def __getattr__(name: str) -> Any:
    module = _NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far, without loading any of them."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if TYPE_CHECKING:
    from cad.build123d._flatten import (flat_pattern, flatten_face, flatten_faces, offset_profile, planar_faces,
                                        union_faces)
    from cad.build123d._geometry import (ClosestPoints, GeometryError, GeometryIssue, MassProperties,
                                         boundary_edges, closest_points, is_sound, mass_properties, overlap_volume,
                                         self_intersections, topology_errors)
    from cad.engine.mechanism import gear_pair, posed, rack_and_pinion_pair, screw_pair
    from cad.engine.model import animation, configuration_sequence, mechanism_state, memo, paint
