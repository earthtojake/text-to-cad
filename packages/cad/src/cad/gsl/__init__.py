"""``cad.gsl``: the GSL document type (``cad.registry``), an implicit (signed-distance) model in omega-core's
language.

A ``.gsl`` is a field: negative inside the part, with booleans, blends, lattices and offsets as arithmetic on
fields. No decorator: a model is authored as text, not made by a script. It is shown as it is, the page marching
the field itself, and it is asked about through the field while it is written (``cad run gsl eval``, ``cad run gsl
render``: omega's own ``gsl``, the omega integration's, ``cad.omega``).

Two of its operations are for the mesh, which is a translation of the field for something that needs triangles and
is made when one is wanted, not on every edit. ``gsl`` writes a mesh it got wrong as readily as a right one, so
both hold the mesh to the field:

- ``validate`` (``cad gsl validate part.gsl``) meshes the model as ``gsl`` does by default, or takes the mesh
  given, and judges it (``cad.omega._check``).
- ``mesh`` (``cad gsl mesh part.gsl part.glb``) meshes it, with values for its names, into a GLB that is written
  only once it has passed the same judgement, and keeps it by what made it (``cad.omega._mesh``).

The other two hold exact parts to the concept's field, with no mesh of the concept (``cad.omega._fit``):

- ``fit`` (``cad gsl fit enclosure.gsl ID``): exact parts fitted around a concept part, each part's clearance,
  where one runs into its material, and the contacts the design means.
- ``bake`` (``cad gsl bake part.gsl ID``): an exact part baked from the concept, checked against its field both
  ways, the concept kept as baked; ``--stale`` says where the concept has moved since.

A model's script says which of its parts are concepts, so an assembly holds exact parts and concepts together
and the document carries which is which (``cad.engine.declarations.CONCEPT``); neither is a command:

- ``concept("enclosure.gsl")`` is a part with no shape of its own, placed as any part is: the viewer draws its
  field among the exact parts, and ``fit`` and ``bake`` given the assembly alone find it there.
- ``baked(knob, "knob.gsl")`` says an exact part was made from a concept, which stays its other representation.

Each command is a generated MIRROR of its function. Everything loads on first use: ``import cad.gsl`` imports no
omega_core. A function called where the integration's extra is missing says so by name (``cad[omega]``).
"""

from __future__ import annotations

from pathlib import Path

from cad._internal.document_type import bind as _bind
from cad.results import CheckResult

__all__ = ["bake", "baked", "concept", "fit", "mesh", "validate"]

SUFFIX = ".gsl"


def concept(path: Path, *, label: str | None = None, **values: float):
    """A GSL concept as a part of an assembly: a part with no shape of its own, placed as any part is
    (``.moved(Location(...))``, a child of a ``Compound``). The concept is written in the part's own frame.

    path: the .gsl concept.
    label: the part's name in the assembly; the file's stem where none is given.
    values: a value for one of the concept's top-level names (``wall=2.5``), this placement's.
    """
    from cad.engine.concepts import concept_part

    return concept_part(path, label, values)


def baked(part, path: Path, **values: float):
    """Say an exact part was baked from a GSL concept, which stays its other representation: the viewer shows
    either, and ``bake`` given the assembly holds the part to it. Returns ``part``.

    part: the exact part, a build123d shape; not an assembly.
    path: the .gsl concept it was made from, written in the part's own frame.
    values: the values of the concept's top-level names it was baked with (``lobes=7``).
    """
    from cad.engine.concepts import baked_part

    return baked_part(part, path, values)


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


def fit(path: Path, exact: str | None = None, *, contact: tuple[str, ...] = (), define: tuple[str, ...] = (),
        tolerance: float = 0.01, contact_radius: float = 3.0, density: float = 4.0, chord: float = 0.01,
        strict: bool = False, verbose: bool = False) -> CheckResult:
    """Check exact parts against a GSL concept part they must fit with, through its field, with no mesh of it.

    The exact parts' surfaces are sampled by area (every vertex and about ``density`` points a square
    millimetre) and each point is scored by the concept's field: each part's clearance is the least value over
    its surface, and a part whose surface goes below ``-tolerance`` runs into the concept's material, an error.
    A ``contact`` is a point where the design means a part to touch the concept (a board on a standoff): the
    exact surface within ``contact_radius`` of it must lie on the concept's surface, within ``tolerance``.
    Clearance alone never shows a contact is missing. The concept is written in the exact parts' frame. Its own
    features that no exact part comes near are not judged: look at its picture.

    Given an assembly alone (a document id or an .xbf whose model names its concepts, ``cad.gsl.concept``), every
    exact part is held to each part that is a concept, each where the assembly places it and with the values it
    gives it there; a place is then said in that concept's own frame, and no ``contact`` or ``define`` is taken.

    path: the .gsl concept; or, alone, the assembly that names its concepts: a document id or an .xbf.
    exact: the exact parts: a document id (cad run prints it), an .xbf, a .step, or a .glb.
    contact: a point x,y,z (mm) where an exact part should touch the concept; repeat it for several.
    define: a value for one of the concept's top-level names, as name=number (r=6.5); repeat it for several.
    tolerance: mm within which a field value is the concept's surface.
    contact_radius: mm about a contact's point in which the exact surface is looked for.
    density: points sampled a square millimetre of exact surface, besides its vertices.
    chord: mm chord tolerance an id, .xbf or .step is meshed at to be sampled.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    from cad.omega._fit import assembly, fit as fitted

    if exact is None:
        return assembly("fit", path, contact=contact, define=define, tolerance=tolerance, contact_radius=contact_radius,
                        density=density, chord=chord, strict=strict, verbose=verbose)
    return fitted(path, exact, contact=contact, define=define, tolerance=tolerance, contact_radius=contact_radius,
                  density=density, chord=chord, strict=strict, verbose=verbose)


def bake(path: Path, exact: str | None = None, *, stale: bool = False, define: tuple[str, ...] = (), max_deviation: float = 0.0,
         tolerance: float = 0.01, density: float = 4.0, chord: float = 0.01, strict: bool = False,
         verbose: bool = False) -> CheckResult:
    """Check an exact part baked from a GSL concept against the concept's field, both ways, and keep the concept
    as baked; with ``stale``, say where the concept has moved since.

    One way, the exact surface sampled by area is scored by the concept's field: signed, so below zero the
    concept carries material the exact part does not (a blend's nominal departure is the usual one) and above it
    the exact part carries more. The other, points on the concept's surface (omega's ``surface``, over both
    shapes' box) are measured to the exact triangles. Each part's largest departure is said, and where; none
    fails the bake unless it passes ``max_deviation``. A bake that passes keeps a copy of the concept, with the
    values given, as ``<stem>.baked.gsl`` beside it. ``stale`` instead scores the exact surface with the concept
    as it is now and as it was kept, and fails where the two differ by more than ``tolerance``, saying by how
    much and over what region of which part, so the change can be baked. A file the concept imports is not kept.

    Given an assembly alone (a document id or an .xbf whose model says which parts were baked, ``cad.gsl.baked``),
    each such part is held to its own concept, alone, in the part's own frame, with the values the assembly gives;
    no ``define`` is taken.

    path: the .gsl concept; or, alone, the assembly that names its baked parts: a document id or an .xbf.
    exact: the exact part: a document id (cad run prints it), an .xbf, a .step, or a .glb.
    stale: hold the concept as it is now to the copy kept at its last bake, instead of baking.
    define: a value for one of the concept's top-level names, as name=number (r=6.5); repeat it for several.
    max_deviation: mm the exact part may depart from the concept, either way, before the bake fails (0: no limit).
    tolerance: mm within which a field value is the concept's surface, and a change is no change.
    density: points sampled a square millimetre of exact surface, besides its vertices.
    chord: mm chord tolerance an id, .xbf or .step is meshed at to be sampled.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    from cad.omega._fit import assembly, bake as baked_from

    if exact is None:
        return assembly("bake", path, define=define, stale=stale, max_deviation=max_deviation, tolerance=tolerance,
                        density=density, chord=chord, strict=strict, verbose=verbose)
    return baked_from(path, exact, stale=stale, define=define, max_deviation=max_deviation, tolerance=tolerance,
                 density=density, chord=chord, strict=strict, verbose=verbose)


# ``validate`` takes an option named ``mesh`` (the STL to judge), so the operation is defined under another name
# and published as ``mesh``: the two never meet in one scope.
_mesh.__name__ = _mesh.__qualname__ = "mesh"
mesh = _mesh
del _mesh

_bind(__name__)
