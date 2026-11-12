"""``cad.omega``: the omega integration -- our code that runs omega-core's ``gsl``, the compiler and mesher of GSL,
Gradient Control Laboratories' language for implicit (signed-distance) models (its extra, ``cad[omega]``: the
``omega-core`` wheel, which carries ``gsl`` for macOS and Linux and a standard-library client for its field
queries, ``omega_core``).

A ``.gsl`` is omega's own file and no document type: an agent writes one as text, ``gsl`` compiles it, and the
mesh ``gsl`` writes is an STL, which is one. What the tool already does stays the tool's: ``cad run gsl compile
-t stl part.gsl`` meshes, ``cad run gsl render part.gsl`` draws the field, ``cad run gsl eval`` and
``omega_core.Session`` answer field queries (``_command``).

What is missing without us is the guarantee: ``gsl`` exits 0 on a mesh that is empty, open, non-manifold,
inside-out, cut off at its box or missing a wall thinner than a cell. ``check`` (``cad omega check part.gsl``,
the integration's one operation in ``cad.registry``) meshes the model as ``gsl`` does by default, or takes the
mesh given, and judges it against the field itself (``_check``).

Everything loads on first use: ``import cad.omega`` imports no omega_core. A helper called where the extra is
missing says so by name (``cad[omega]``), as every integration's does.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import CheckResult

__all__ = ["check"]


def check(path: Path, *, mesh: Path | None = None, strict: bool = False, verbose: bool = False) -> CheckResult:
    """Mesh one GSL model with omega's ``gsl`` and check the mesh against the model's field.

    ``gsl`` exits 0 on a mesh it got wrong, so each is judged here: it compiles; it has triangles; every
    edge is shared by exactly two of them (no holes, nothing non-manifold); it encloses a positive volume
    (not inside-out); it stops short of the ``@scene`` box (not cut off: a model needs ``@scene``, without
    which ``gsl`` guesses the box); and its volume lies within the bracket omega's evaluator proves for the
    field (nothing thinner than a cell lost). Zero-area triangles are a warning. Errors always block; under
    ``strict`` warnings do too.

    path: the .gsl model to check.
    mesh: an STL of this model to judge instead of meshing it here (one written by `gsl compile -t stl`).
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    from cad.omega._check import check as _check

    return _check(path, mesh=mesh, strict=strict, verbose=verbose)
