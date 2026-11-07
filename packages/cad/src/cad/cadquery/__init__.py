"""``cad.cadquery``: the cadquery integration -- our code for CadQuery, a Python CAD library on an OCP build
of its own.

CadQuery pins ``cadquery-ocp`` 7.9 and the engine's kernel (build123d) ``cadquery-ocp-novtk`` 8.0, and both
are the one ``OCP`` module: CadQuery can never share a process with the engine's workers. So the integration
runs in a separate process -- the environment of its extra, ``cad[cadquery]``: the library's core and
CadQuery, which ``cad run`` makes for a program that imports ``cadquery`` -- and what crosses to the engine
is a description, never a CadQuery object. A CadQuery program hands its result over:

.. code-block:: python

    import cadquery as cq
    from cad import model

    def bracket():
        return cq.Workplane("XY").box(40, 20, 6).faces(">Z").workplane().hole(8)

    if __name__ == "__main__":
        model(bracket(), name="bracket")     # a document: its id, its page, every export

``model(value, name=...)`` takes a ``Workplane`` (the shapes on its stack), a ``Shape``, a ``Sketch`` (its
faces) or an ``Assembly`` (its tree: names, colours and the solved locations), through this integration's
producer of the ``model`` document type (``_producers``), a portable one: ``_bridge`` describes the value as
the engine's reader describes a STEP -- the assembly tree as data, every part's shape and placement in one
BinTools dump written by CadQuery's own OCP (``cad.engine.reader.pack``) -- and the engine's kernel process
reads it (``cad.engine.portable``) and makes the document, held, cached, served and exported as any shape
handed over is. Nothing of CadQuery enters the engine's processes, and no CadQuery object is ever a model
body's result: ``@model`` on a CadQuery function runs in a worker, which has no CadQuery.

Importing this package imports no CadQuery and no OCP; ``is_cadquery`` reads a value's type names alone.
"""

from __future__ import annotations

from cad.cadquery._bridge import is_cadquery, kind_of

__all__ = ["is_cadquery", "kind_of"]
