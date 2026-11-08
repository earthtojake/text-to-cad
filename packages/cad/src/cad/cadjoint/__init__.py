"""``cad.cadjoint``: the cadjoint integration -- our helpers that take cadjoint's objects.

cadjoint is an implicit CAD kernel on JAX: a part is a signed distance field (``cadjoint.sdf.SDF``), built
of blended booleans, shells, offsets, patterns and sketches extruded, revolved or lofted. Its extra is
``cad[cadjoint]``; its code runs in the process that calls it. The solids it hands back are build123d's,
so a program that uses it needs the build123d integration beside it, and gets it
(``cad.registry.INTEGRATIONS["cadjoint"].needs``). It re-exports nothing of cadjoint
(``from cadjoint.sdf import Shell`` stays cadjoint's):

- ``solid(scene, cell=)``: the field as one build123d ``Solid`` of planar triangles, which a model returns
  as any other shape -- so its document, view, snapshot, exports and checks are every solid's. The
  surface is meshed by cadjoint's own dual contouring at ``cell`` millimetres, refused where it is not one
  closed body, and simplified by cadjoint's feature-preserving collapse to within ``cell / 20``;
- ``field(scene, cell=)``: the field with its sampling, which a function declared ``@implicit`` returns
  (``Field``): the engine samples it once -- the same sampling and the same refusals as ``solid``'s, with
  nothing simplified and no B-rep -- and holds the mesh as the model's document (the ``implicit`` document
  type), its producer this integration's (``_producers``, ``_document``);
- ``section(scene, out, axis=, at=)``: a plane through the field drawn as a PNG -- inside blue, outside
  orange, iso-distance contours and the surface itself in black -- and what it shows (``Section``): how
  far everything is from the surface, read without meshing (a wall's thickness, a blend's reach).

Everything loads on first use: ``import cad.cadjoint`` imports no cadjoint and no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Each name and the module that defines it.
_NAMES = {
    "solid": "cad.cadjoint._solid",
    "field": "cad.cadjoint._field",
    "Field": "cad.cadjoint._field",
    "section": "cad.cadjoint._section",
    "Section": "cad.cadjoint._section",
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
    from cad.cadjoint._field import Field, field
    from cad.cadjoint._section import Section, section
    from cad.cadjoint._solid import solid
