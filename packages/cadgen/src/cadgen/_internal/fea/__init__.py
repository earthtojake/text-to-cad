"""Linear static finite element analysis behind ``cadgen fea``.

The public verbs live in :mod:`cadgen.fea`; this package is the mechanism:

* :mod:`.study` -- the study file (material, fixtures, loads, mesh, output),
  parsed and checked before any heavy import;
* :mod:`.materials` -- the built-in material table;
* :mod:`.mesh` -- STEP occurrence -> quadratic tetrahedra through netgen, with
  every B-rep face kept under its cadgen ordinal;
* :mod:`.solve` -- assembly, boundary conditions and the solve (scikit-fem +
  pyamg), then stress recovery;
* :mod:`.outputs` -- the result files: a vertex-coloured GLB the viewer already
  renders, a JSON sidecar with the numbers, an optional VTU;
* :mod:`.run` -- the orchestration the verbs call.

Everything numeric imports lazily, inside the functions that need it, so that
``cadgen fea --help`` and the public namespace stay off the CAD kernel and off
the solver stack (the ``fea`` extra may not be installed).

Units throughout: mm, N, MPa (N/mm^2), tonne/mm^3 for density.
"""
