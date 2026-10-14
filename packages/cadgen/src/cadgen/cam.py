"""The public ``cam`` namespace: toolpaths and G-code for a saved part.

Two verbs, each mirrored by a generated CLI (``cadgen cam features``,
``cadgen cam plan``; README law 6):

* ``features`` lists what a CAM job can name on a part: every face with its
  ``#o1.fN`` selector and a machining reading (a flat floor at Z, a wall, a hole
  of a diameter and depth on an axis), plus the part's bounding box. For a DXF,
  its closed profiles and holes.
* ``plan`` reads a job (machine, material, stock, tools, setups and their
  operations), plans every operation's toolpath, simulates the cut, checks it and
  posts G-code for the named controller. It writes ``<stem>.cam.glb`` (the part,
  the simulated stock and the toolpaths, with the verdict in its extras) and one
  ``<stem>.<setup>.<ext>`` per setup beside the part, or in ``out_dir``.

There is no decorator: a job is about a document (the saved STEP or DXF), and
CLIs take documents only (law 7). A plan that cannot run writes nothing.

Import discipline: nothing here may pull in OCP, build123d, ezdxf or shapely at
module scope (see :mod:`cadgen.step`) -- ``--help`` must stay cheap. Each verb
imports the engine (:mod:`cadgen._internal.cam.run`) inside its body.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import CamFeaturesResult, CamPlanResult

__all__ = ["features", "plan"]


def features(target: Path, *, occurrence: str | None = None, direction: str | None = None) -> CamFeaturesResult:
    """List what a CAM job can name on a part: faces with their selectors and a machining reading, holes, floors.

    target: the STEP/STP document holding the part, or a DXF of flat profiles.
    occurrence: which part occurrence to read (``#o1.2``) when the document is an
        assembly. Omitted, the document must hold one part.
    direction: list only what a tool coming from this side can work (``+Z``, ``-Z``,
        ``+X``...): the holes it reaches, the floors and faces turned toward it, the
        walls along it. A feature no direction lists is an undercut.
    """
    from cadgen._internal.cam.run import list_features

    return list_features(Path(target), occurrence=occurrence, direction=direction)


def plan(target: Path, *, job: str | dict | None = None, occurrence: str | None = None, post: str | None = None,
         out_dir: Path | None = None, verbose: bool = False) -> CamPlanResult:
    """Plan a CAM job on a part: toolpaths, a simulated cut, checks, and G-code per setup.

    target: the STEP/STP document holding the part, or a DXF of flat profiles.
    job: the job: a JSON file path, inline JSON, or (library callers) a dict. It
        names the machine (kind and post), the material, the stock, the tools and
        the setups, each with its operations; see the cam skill for the schema.
        Face refs are the ones ``cadgen cam features`` prints.
    occurrence: which part occurrence to machine (``#o1.2``) when the document is an
        assembly. Omitted, the document must hold one part.
    post: write the G-code for this post instead of the job's ``machine.post``
        (``haas``): the same job for another controller, without editing it.
    out_dir: where the result GLB and the posted files go. Omitted, they go beside
        the document, as ``<stem>.cam.glb`` and ``<stem>.<setup>.<ext>``.
    verbose: show every progress line and the timings on stderr.
    """
    from cadgen._internal.cam.run import plan_job

    return plan_job(Path(target), job=job, occurrence=occurrence, post=post,
                    out_dir=None if out_dir is None else Path(out_dir), verbose=verbose)
