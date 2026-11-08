"""The cadjoint integration's producer: an implicit field, declared with its sampling, made into the
``implicit`` document type.

``@implicit`` on a function returning ``cad.cadjoint.field(scene, cell=...)`` -- a cadjoint SDF with the
cell it is sampled at and, where the caller gives one, its bounds -- makes a document the engine holds as
the mesh sampled from the field, with no file behind it (``cad.registry``). The matcher reads the returned
value's class name and module alone, so asking which producer takes a value imports no cadjoint.
"""

from __future__ import annotations

from typing import Any

from cad.registry import Producer

__all__ = ["PRODUCERS", "is_field"]


def is_field(value: Any) -> bool:
    """Whether ``value`` is a ``cad.cadjoint.Field`` (``cad.cadjoint.field(scene, cell=...)``), by its class's
    name and module: no import of cadjoint."""
    return any(cls.__name__ == "Field" and str(cls.__module__).split(".")[:2] == ["cad", "cadjoint"]
               for cls in type(value).__mro__)


PRODUCERS: tuple[Producer, ...] = (
    Producer("implicit", "cadjoint", "a cad.cadjoint.field(scene, cell=...) a model returns", is_field,
             "cad.cadjoint._document", ("triangles",)),
)
