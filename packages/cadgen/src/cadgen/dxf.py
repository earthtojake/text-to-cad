"""The public ``dxf`` format namespace: the ``@dxf`` decorator and its verbs.

``@dxf`` DECLARES a drawing; ``dxf.snapshot(...)`` renders one. They are the
same object — this module is callable (see
:mod:`cadgen._internal.format_namespace`) — so the drawing family is one table
row like every other format (design/format-doors.md).

**There is no ``dxf.build``** (deleted, hard cutover). A ``.dxf`` has no derived
state a door must materialize: the file IS the product, and both the CAD Viewer
and snapshot draw it from the same server-side 2D payload
(:mod:`cadgen.drawing_payload`). Drawings are made the way every model is made —
by running the script: ``python drawing.py``.

Import discipline: nothing here may pull in ezdxf/OCP at module scope (see
:mod:`cadgen.step`).
"""

from __future__ import annotations

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import drawing_snapshot_verb

__all__ = ["snapshot"]

#: ``cadgen dxf snapshot``'s verb: draw a ``.dxf`` flat, as the viewer draws it.
snapshot = drawing_snapshot_verb("dxf")


def __getattr__(name: str):
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


callable_namespace(__name__, "dxf")
