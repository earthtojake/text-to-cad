"""The CAM engine behind :mod:`cadgen.cam`: a job in, toolpaths, a simulated cut, checks and G-code out.

The modules and the one contract between them:

* :mod:`.job` parses and validates the job (closed vocabulary, teaching errors) into frozen dataclasses;
  :mod:`.wcs` turns a setup's orientation and origin into the work coordinate system; :mod:`.tools` gives every
  tool its cutter profile; :mod:`.feeds` the starting-point speeds and feeds.
* :mod:`.part` reads the STEP (or DXF) once: exact faces through ``read_scene`` and one tessellation with each
  triangle's face; :mod:`.features` reads holes, floors and walls off it.
* :mod:`.ir` is THE contract: the Toolpath IR every planner emits and the simulator, the checks, the posts and the
  GLB consume. Nothing downstream re-reads a planner's internals.
* :mod:`.operations` (a lazy registry of every operation) plans; :mod:`.geom2d` and :mod:`.linking` are the
  planners' shared geometry; :mod:`.stock` (a lazy registry of stock simulators by machine kind) simulates;
  :mod:`.checks` (a lazy registry of every check) judges; :mod:`.posts` (a lazy registry of every controller) posts;
  :mod:`.fit` adapts the run to its budget; :mod:`.outputs` writes the GLB; :mod:`.run` orchestrates.

Stdlib at import throughout: numpy, shapely and OCP load inside the functions that need them.
"""
