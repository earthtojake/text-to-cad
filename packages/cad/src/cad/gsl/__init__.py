"""``cad.gsl``: the GSL document type (``cad.registry``), an implicit (signed-distance) model in omega-core's
language.

A ``.gsl`` is a field: negative inside the part, with booleans, blends, lattices and offsets as arithmetic on
fields. No decorator: a model is authored as text, not made by a script. It is shown as it is, the page marching
the field itself, and it is asked about through the field while it is written (``cad run gsl eval``, ``cad run gsl
render``: omega's own ``gsl``, the omega integration's, ``cad.omega``).

Its two operations are for the mesh, which is a translation of the field for something that needs triangles and
is made when one is wanted, not on every edit. ``gsl`` writes a mesh it got wrong as readily as a right one, so
both hold the mesh to the field:

- ``validate`` (``cad gsl validate part.gsl``) meshes the model as ``gsl`` does by default, or takes the mesh
  given, and judges it (``cad.omega._check``).
- ``mesh`` (``cad gsl mesh part.gsl part.glb``) meshes it, with values for its names, into a GLB that is written
  only once it has passed the same judgement, and keeps it by what made it (``cad.omega._mesh``).

Each command is a generated MIRROR of its function. Everything loads on first use: ``import cad.gsl`` imports no
omega_core. A function called where the integration's extra is missing says so by name (``cad[omega]``).
"""

from __future__ import annotations

from pathlib import Path

from cad._internal.document_type import bind as _bind
from cad.results import CheckResult

__all__ = ["mesh", "validate"]

SUFFIX = ".gsl"


def validate(path: Path, *, mesh: Path | None = None, strict: bool = False, verbose: bool = False) -> CheckResult:
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


def _mesh(path: Path, out: Path | None = None, *, define: tuple[str, ...] = (), depth: int | None = None,
          strict: bool = False, verbose: bool = False) -> CheckResult:
    """Mesh one GSL model into a GLB with omega's ``gsl``, checked against the model's field, and keep it.

    A model is asked about through its field while it is written (``cad run gsl eval``, ``cad run gsl
    render``); this is for when a file of triangles is wanted. The mesh is one indexed GLB, a node for each
    of the model's returns, with a normal at every vertex from the field's gradient. It is judged as
    ``validate`` judges one -- it has triangles, every edge is shared by exactly two, it encloses a positive
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
    from cad.omega._mesh import mesh as made

    return made(path, out, define=define, depth=depth, strict=strict, verbose=verbose)


# ``validate`` takes an option named ``mesh`` (the STL to judge), so the operation is defined under another name
# and published as ``mesh``: the two never meet in one scope.
_mesh.__name__ = _mesh.__qualname__ = "mesh"
mesh = _mesh
del _mesh

_bind(__name__)
