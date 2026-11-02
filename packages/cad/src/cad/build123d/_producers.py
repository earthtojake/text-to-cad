"""The build123d integration's producers: a build123d shape made into each document type it writes.

One producer per document type a decorator writes (``@xbf``, ``@step``, ``@glb``, ``@stl``,
``@threemf``, ``@dxf``) and the document of an ``@model``, each registered in ``cad.registry``. A
producer's matcher reads the returned value's type names and modules alone -- ``build123d``'s
``Shape`` anywhere in its class's ancestry -- so asking which producer takes a value imports no
kernel. The writer is the engine code the file comes from: the XCAF document the engine makes of
the shape (``cad.engine.document``), and each other file a translation of it
(``cad.engine.export.translate``).
"""

from __future__ import annotations

from typing import Any

from cad.registry import Producer

__all__ = ["PRODUCERS", "is_shape"]


def is_shape(value: Any) -> bool:
    """Whether ``value`` is a build123d ``Shape`` (a Solid, a Compound, a Sketch, a Face, ...), by its
    class's ancestry: no import of build123d."""
    return any(cls.__name__ == "Shape" and str(cls.__module__).split(".")[0] == "build123d"
               for cls in type(value).__mro__)


_ACCEPTS = "a build123d Shape"
_DOCUMENT = ("geometry", "assembly", "names", "colours", "materials", "element names", "mechanism",
             "configuration sequences")
_TRANSLATE = "cad.engine.export.translate"

PRODUCERS: tuple[Producer, ...] = (
    Producer("xbf", "build123d", _ACCEPTS, is_shape, "cad.engine.document",
             (*_DOCUMENT, "animations", "build closure")),
    Producer("step", "build123d", _ACCEPTS, is_shape, _TRANSLATE, _DOCUMENT),
    Producer("glb", "build123d", _ACCEPTS, is_shape, _TRANSLATE,
             ("triangles", "assembly", "names", "colours", "materials", "animations")),
    Producer("stl", "build123d", _ACCEPTS, is_shape, _TRANSLATE, ("triangles",)),
    Producer("threemf", "build123d", _ACCEPTS, is_shape, _TRANSLATE,
             ("triangles", "assembly", "names", "colours", "materials")),
    Producer("dxf", "build123d", "a planar build123d Shape (a sketch, a face, wires or edges)", is_shape, _TRANSLATE,
             ("2D geometry", "layers")),
)
