"""``cad.omega``: the omega integration -- our code that runs omega-core's ``gsl``, the compiler and mesher of GSL,
Gradient Control Laboratories' language for implicit (signed-distance) models (its extra, ``cad[omega]``: the
``omega-core`` wheel, which carries ``gsl`` for macOS and Linux and a standard-library client for its field
queries, ``omega_core``).

A GSL model is a document type of its own (``cad.gsl``); this is the tool behind it. What ``gsl`` already does
stays ``gsl``'s: ``cad run gsl compile -t stl part.gsl`` meshes, ``cad run gsl render part.gsl`` draws the field,
``cad run gsl eval`` and ``omega_core.Session`` answer field queries (``_command``). The program is found here
(``_program``: ``CAD_GSL``'s, else the extra's, never one on PATH).

What is missing without us is the guarantee: ``gsl`` exits 0 on a mesh that is empty, open, non-manifold,
inside-out, cut off at its box or missing a wall thinner than a cell. The type's two operations give it, and
their code is here: ``cad.gsl.validate`` judges a mesh against the field itself (``_check``), and ``cad.gsl.mesh``
writes one, with values for the model's names, only once it has passed, and keeps it (``_mesh``).

Everything loads on first use: ``import cad.omega`` imports no omega_core. A helper called where the extra is
missing says so by name (``cad[omega]``), as every integration's does.
"""

from __future__ import annotations

__all__: list[str] = []
