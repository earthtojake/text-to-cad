"""``cad.openscad``: the openscad integration -- our code for OpenSCAD, the script-based CSG modeller.

OpenSCAD is an external program our code runs (kind C), in a separate process, with no extra: nothing on
PyPI carries it, so the person installs it and the probe finds it (``cad.registry.INTEGRATIONS["openscad"]``).
Its kernel makes triangle meshes (CGAL, Manifold in the snapshots) and no B-rep, so what it renders is a
mesh and nothing of exact geometry: a ``.scad`` program is the ``scad`` document type (``cad.scad``), SOURCE
the agent edits as text, and every view, export, still and manufacturing check of one reads the mesh
OpenSCAD renders of it. What is here:

* ``_program``: OpenSCAD's command line found and run headless, by the library's one helper for external
  programs (``cad._internal.programs``): ``CAD_OPENSCAD``, refused unless it names an openscad, then
  ``PATH``, then where its installer puts it; its version asked and checked (2021.01 or newer); every run
  with no display and private homes -- but the person's OpenSCAD libraries kept reachable, since an
  ``include`` of one is an input of the program, not a setting (``libraries``, ``OPENSCADPATH``).
* ``_render``: one render of a program to a binary STL in a private folder, moved into place atomically
  (``render``); the files it read (``-d``, the dependency file), for the key of what is kept of it
  (``key``); a failure said in OpenSCAD's words, a 2D program refused in one line.

There is no helper here that a model calls: a program's mesh is read by its type (``scad.read``), as an
STL's is. Importing this package starts nothing and runs no OpenSCAD.
"""

from __future__ import annotations

__all__: list[str] = []
