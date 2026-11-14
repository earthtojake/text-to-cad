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

A model is asked about through its field, and meshed when a file is wanted, not on every edit. ``mesh`` (``cad
omega mesh part.gsl part.glb``) is that step: omega's evaluator meshes the model, with values for its names, into
a GLB, the mesh is judged as ``check`` judges one before it is written, and one that passed is kept by what made
it, so the same model and values are meshed once (``_mesh``).

Everything loads on first use: ``import cad.omega`` imports no omega_core. A helper called where the extra is
missing says so by name (``cad[omega]``), as every integration's does.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import CheckResult

__all__ = ["check", "mesh"]


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


def mesh(path: Path, out: Path | None = None, *, define: tuple[str, ...] = (), depth: int | None = None,
         strict: bool = False, verbose: bool = False) -> CheckResult:
    """Mesh one GSL model into a GLB with omega's ``gsl``, checked against the model's field, and keep it.

    A model is asked about through its field while it is written (``cad run gsl eval``, ``cad run gsl
    render``); this is for when a file of triangles is wanted. The mesh is one indexed GLB, a node for each
    of the model's returns, with a normal at every vertex from the field's gradient. It is judged as
    ``check`` judges one -- it has triangles, every edge is shared by exactly two, it encloses a positive
    volume, it stops short of the ``@scene`` box, and its volume lies within the bracket omega's evaluator
    proves for the field -- and one that fails is not written. One that passes is kept by the model's
    bytes, the files it imports, the values and the depth, so the same question is answered from what is
    kept (``measurements["cached"]``). The file is ``measurements["glb"]``.

    path: the .gsl model to mesh.
    out: where to write the GLB; without it the mesh is left where cad keeps it, and named in the result.
    define: a value for one of the model's top-level names, as name=number (r=6.5); repeat it for several.
    depth: the mesher's octree depth (gsl's own is 9); one more halves the cell and takes about four times as long.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    from cad.omega._mesh import mesh as _mesh

    return _mesh(path, out, define=define, depth=depth, strict=strict, verbose=verbose)
