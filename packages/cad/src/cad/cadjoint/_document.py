"""The cadjoint producer's writer: a field sampled and written as the ``implicit`` document's bytes.

``document(declared, name, closure=)`` samples the field (``_field.sample``: the one sampling, with its
refusals) and hands the engine the sample -- the vertices, the field's normals at them and the triangles --
which the engine writes as the document the daemon holds (``cad.engine.implicit_document``: a GLB, the closure and
the field's digest in its ``asset.extras``). The engine imports nothing of cadjoint: this module is named
by the producer (``cad.registry``) and imported in the worker that builds the model, where cadjoint is.
"""

from __future__ import annotations

from typing import Any

from cad.cadjoint._field import Field, Sampled, sample

__all__ = ["document", "sampled"]


def sampled(declared: Any) -> Sampled:
    """The field a model returned, sampled for its document (``_field.sample``); a ``TypeError`` for anything
    but a ``Field`` (``cad.cadjoint.field(scene, cell=...)``)."""
    if not isinstance(declared, Field):
        raise TypeError("an implicit document is made of cad.cadjoint.field(scene, cell=...), not "
                        f"{type(declared).__module__}.{type(declared).__qualname__}")
    return sample(declared, where="cad.cadjoint.field")


def document(declared: Any, name: str, *, closure: str | None = None) -> tuple[bytes, dict[str, Any]]:
    """The implicit document of the field a model returned: its GLB bytes, and its facts (the run line's
    delta: ``triangles``, ``bounds``, ``volume``, the thinnest wall)."""
    from cad.engine import implicit_document as implicit

    found = sampled(declared)
    return implicit.document_bytes(name, found.positions, found.normals, found.triangles, closure=closure,
                                   digest=declared.digest, cell=found.cell, wall=found.wall_mm)
