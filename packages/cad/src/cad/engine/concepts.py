"""A GSL concept as a part of a model (``cad.gsl.concept``, ``cad.gsl.baked``): the part with no shape that is
its concept, and the exact part that names the concept it was made from. What each keeps is
``declarations.CONCEPT``, which the document carries on the part (``document.DECLARED``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cad.engine.declarations import CONCEPT, concept_value

__all__ = ["baked_part", "concept_part"]

SUFFIX = ".gsl"


def _declared(path: Any, role: str, values: dict) -> dict:
    """What a part's concept is kept as (``declarations.concept_value``). The file is read here, in the model's
    body, so the build is made again when it changes, and the document says which text it meant."""
    import hashlib

    target = Path(path).expanduser().resolve()
    if target.suffix.lower() != SUFFIX:
        raise ValueError(f"a concept is a {SUFFIX} file, not {target.name}")
    if not target.is_file():
        raise FileNotFoundError(f"the concept {target} is not there")
    digest = hashlib.blake2b(target.read_bytes(), digest_size=16).hexdigest()
    return concept_value({"gsl": target.as_posix(), "role": role, "digest": digest, "values": dict(values)},
                         target.name)


_SHAPELESS = None


def _shapeless(named: str) -> Any:
    """A part with no shape: an empty compound of its own. Each concept has one to itself (``named``, what it
    is: its label, file and values): a document holds one part for one shape, so concepts sharing an empty shape
    would be one part there, the last one's name and concept on all of them. Made under the engine's memo, so
    the model that holds it is replayed as any other is."""
    global _SHAPELESS
    if _SHAPELESS is None:
        from cad.engine.model import memo

        @memo
        def shapeless(named: str) -> Any:
            import build123d as bd
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Compound

            empty = TopoDS_Compound()
            BRep_Builder().MakeCompound(empty)
            return bd.Compound(empty)

        _SHAPELESS = shapeless
    return _SHAPELESS(named)


def concept_part(path: Any, label: str | None, values: dict) -> Any:
    declared = _declared(path, "body", values)
    name = label or Path(path).stem
    part = _shapeless(json.dumps([name, declared], sort_keys=True))
    part.label = name
    part.__dict__[CONCEPT] = declared
    return part


def baked_part(part: Any, path: Any, values: dict) -> Any:
    import build123d as bd

    if not isinstance(part, bd.Shape):
        raise TypeError(f"baked: a build123d shape, not {type(part).__name__}")
    if part.__dict__.get("_NodeMixin__children"):
        raise ValueError(f"baked: {part.label or 'the shape'} is an assembly; name the concept on the part made from it")
    part.__dict__[CONCEPT] = _declared(path, "baked", values)
    return part
