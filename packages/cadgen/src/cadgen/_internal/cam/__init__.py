"""The CAM behind :mod:`cadgen.cam`: a job in; toolpaths and G-code from FreeCAD, checked against the part, out.

* :mod:`.job` parses and validates the job (closed vocabulary, teaching errors) into frozen dataclasses;
  :mod:`.tools` and :mod:`.feeds` give its tools and the starting-point speeds and feeds FreeCAD cuts at.
* :mod:`.part` reads the STEP or xbf once: exact faces through ``read_step``/``read_xbf`` and one tessellation with
  each triangle's face; :mod:`.features` reads holes, floors and walls off it.
* :mod:`.freecad` finds the person's FreeCAD and runs :mod:`.freecad_job` in it, which plans and posts one setup;
  :mod:`.toolpath` reads FreeCAD's paths back as moves.
* :mod:`.checks` judges each plan against the part; :mod:`.outputs` writes the GLB; :mod:`.run` orchestrates.

Stdlib at import throughout: numpy and OCP load inside the functions that need them.
"""
