"""The stress study behind ``cad.<type>.fea`` (``cad <type> fea``), the operation every B-rep type shares
(:mod:`.operation`, which the type's package binds).

:mod:`.study` parses and checks the study file before any heavy import; :mod:`.materials` reads a material, the
study's numbers or the model's own;
:mod:`.mesh` turns a STEP occurrence (or an assembly's glued parts) into tetrahedra through netgen, every B-rep face
kept under its cad ordinal; :mod:`.static` solves it through CalculiX (:mod:`.solve`, :mod:`cad.calculix`) and reads
the answer; :mod:`.checks` says what an engineer would of it; :mod:`.outputs` writes the result GLB and VTU;
:mod:`.run` is the orchestration the operation calls: a study's setup, or its solve.

Everything numeric imports lazily, inside the functions that need it, so that ``cad <type> fea --help`` and the
document type stay off the CAD kernel and off the solver stack (CalculiX, the person's own, may not be installed). Units throughout:
mm, N, MPa (N/mm^2), tonne/mm^3 for density.
"""
