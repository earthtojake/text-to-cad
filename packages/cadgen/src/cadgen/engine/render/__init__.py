"""cadgen's stills drawn by OCCT: an engine document drawn by OCCT's own OpenGL renderer from the
engine's own meshes (the XBM buffers ``mesh.py`` writes and the daemon serves), never a mesh of
OCCT's own; a file no document (a mesh file, a robot) from the buffers its reader made
(``formats/``), and a DXF as a drawing. ``cadgen snapshot`` draws every kind through it.

- ``service.py``: a document held and drawn (``Held``), the daemon's render process per served
  document and per file (``Renders``, ``python -m cadgen.engine.render.service``), and a document
  drawn in this process (``draw_here``).
- ``drawing.py``: a DXF drawn as the viewer's DXF pane draws it, in ``look.py``'s 2D look.
- ``occt.py``: the scene -- the modes, the camera, clip, grid, overlays, Preview -- and the
  prototype's CLI (``python -m cadgen.engine.render.occt``); ``look.py`` the regular display modes'
  look, which ``occt.py`` draws by and ``serve.py`` serves to the viewer (``GET /api/look``);
  ``text.py`` and ``overlay.py`` the annotation's words and Measure's marks, as the page draws them.
- ``explode.py``: the viewer's Explode, ported (held to the viewer by one golden).
- ``shapes.py``: a part's buffer as triangulation-only faces and polygon edges, in one kernel read;
  ``attach.py`` the alternative measured against it.
- ``context.py``: the headless OpenGL context, per platform.
- ``meshes.py``, ``compare.py``: the prototype's harness (buffers from a server, side-by-side sheets).
"""
