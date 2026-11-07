"""The cadquery integration's producer: a CadQuery value handed over as the ``model`` document.

One producer, of the one type with no file: ``model(value, name=...)`` hands a ``Workplane``, ``Shape``,
``Sketch`` or ``Assembly`` over, and the engine's kernel process makes the document of the portable
description ``_bridge.portable`` writes (the producer's ``writer``). No file type's producer: a file
decorator declares a model body's output, and a body runs in a worker, where CadQuery never is -- a CadQuery
document's files are exports of it (``cad model export <id> part.step``). The matcher reads the value's type
names and modules alone (``_bridge.is_cadquery``): asking imports no CadQuery.
"""

from __future__ import annotations

from cad.cadquery._bridge import is_cadquery
from cad.registry import Producer

__all__ = ["PRODUCERS"]

PRODUCERS: tuple[Producer, ...] = (
    Producer("model", "cadquery", "a CadQuery Workplane, Shape, Sketch or Assembly", is_cadquery,
             "cad.cadquery._bridge.portable", ("geometry", "assembly", "names", "colours"), portable=True),
)
