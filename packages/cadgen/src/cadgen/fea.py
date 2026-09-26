"""The public ``fea`` namespace: linear static stress on a STEP part.

Two verbs, each mirrored by a generated CLI (``cadgen fea faces``,
``cadgen fea solve``; design/format-doors.md): ``faces`` lists a part's faces
with the ``#o1.fN`` selectors a study names them by, ``solve`` runs one study
and writes a result GLB the viewer renders (von Mises as vertex colour on the
deformed shape) beside a JSON sidecar with the numbers.

Requires the ``fea`` extra (``pip install 'cadgen[fea]'``): netgen for the
mesh, scikit-fem and pyamg for the solve. Import discipline: nothing here may
pull in OCP, build123d or the solver stack at module scope (see
:mod:`cadgen.step`) -- ``--help`` must stay cheap, and the extra may be absent.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import FeaFacesResult, FeaResult

__all__ = ["faces", "solve"]


def faces(target: Path, *, occurrence: str | None = None, verbose: bool = False) -> FeaFacesResult:
    """List one part's faces: selector, area, centre, surface type and a hint.

    target: the STEP/STP document.
    occurrence: which part occurrence to list (``#o1``) when the document is an
        assembly. Omitted, the document must hold one part.
    verbose: show progress on stderr.
    """
    from cadgen._internal.fea.run import list_faces

    return list_faces(target, occurrence=occurrence, verbose=verbose)


def solve(
    target: Path,
    out: Path | None = None,
    *,
    study: str | dict | None = None,
    mesh_size: float | None = None,
    vtu: bool = False,
    verbose: bool = False,
) -> FeaResult:
    """Run one linear static study and write its result GLB and JSON sidecar.

    target: the STEP/STP document holding the part.
    out: the result .glb path. Omitted, writes ``<document>.fea.glb`` beside the
        document; the sidecar is the same name with ``.json``.
    study: the study: a JSON file path, inline JSON, or (library callers) a
        dict. It names the material, the fixed faces and the loads; see the
        fea skill for the schema. Face refs are the ones ``cadgen fea faces``
        prints.
    mesh_size: target element size in mm, overriding the study's mesh.size_mm.
        Omitted, a fortieth of the part's bounding diagonal.
    vtu: also write a ``.vtu`` of the result for ParaView.
    verbose: show progress and timings on stderr.
    """
    from cadgen._internal.fea.run import solve_study

    return solve_study(target, out, study=study, mesh_size=mesh_size, vtu=vtu, verbose=verbose)
