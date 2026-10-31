"""The public ``cam`` namespace: toolpaths and G-code for a saved part, planned by FreeCAD.

Two verbs, each mirrored by a generated CLI (``cadgen cam features``,
``cadgen cam plan``):

* ``features`` lists what a CAM job can name on a part: every face with its ref
  (the engine's, as ``cadgen inspect`` spells it: ``bracket/face 12``) and a
  machining reading (a flat floor at Z, a wall, a hole of a diameter and depth
  on an axis), plus the part's bounding box.
* ``plan`` reads a job (machine, material, stock, tools, setups and their
  operations) and has FreeCAD's CAM workbench plan each setup's toolpaths and
  post them for the named controller, then checks every path against the part.
  It writes ``<stem>.cam.glb`` (the part, the stock and the toolpaths, with the
  verdict in its extras) and, when nothing is an error, the G-code for each
  setup beside the part, or in ``out_dir``.

``plan`` needs FreeCAD 1.1 or newer, installed by the person (``CADGEN_FREECAD``
names its ``freecadcmd`` where it is not found); ``features`` does not. There is
no decorator: a job is about a file (a STEP or an engine document ``.xbf``),
read here, never through the engine. A plan that cannot run writes nothing.

Import discipline: nothing here may pull in OCP or build123d at module scope --
``--help`` must stay cheap. Each verb imports :mod:`cadgen._internal.cam.run`
inside its body.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import CamFeaturesResult, CamPlanResult

__all__ = ["features", "plan"]


def features(target: Path, *, occurrence: str | None = None) -> CamFeaturesResult:
    """List what a CAM job can name on a part: faces with their selectors and a machining reading, holes, floors.

    target: the STEP/STP or XBF document holding the part.
    occurrence: which part occurrence to read (``kit/arm``, ``pin.2``) when the
        document is an assembly. Omitted, the document must hold one part.
    """
    from cadgen._internal.cam.run import list_features

    return list_features(Path(target), occurrence=occurrence)


def plan(target: Path, *, job: str | dict | None = None, occurrence: str | None = None,
         out_dir: Path | None = None, verbose: bool = False) -> CamPlanResult:
    """Plan a CAM job on a part with FreeCAD: toolpaths, checks against the part, and G-code per setup.

    target: the STEP/STP or XBF document holding the part.
    job: the job: a JSON file path, inline JSON, or (library callers) a dict, all
        lengths in mm, feeds in mm/min, speeds in rpm. "machine": {"post": grbl,
        linuxcnc, mach3, fanuc, centroid, uccnc or smoothie, and "max_rpm" (both
        required), and optionally "travel_mm", "min_rpm", "max_feed_mm_min",
        "rapid_mm_min", "work_offset", "name"}. "material": a feeds-table name (aluminum-6061,
        aluminum-7075, steel-1018, stainless-304, brass, delrin, acrylic, hdpe,
        mdf, hardwood, plywood) or {"name", "surface_m_min", "chipload_mm",
        "drill_mm_per_rev", "stepdown_fraction"}. "stock": {"margin_mm": [x, y,
        z]}, the part's box grown by x and y each side and z over the top.
        "tools": [{"id", "type": flat, ball, bull or drill, "number" (the T
        number), "diameter_mm", "flute_length_mm", "stickout_mm"; a flat, ball or
        bull's "flutes" and "shank_diameter_mm", a bull's "corner_radius_mm", a
        drill's "point_angle"; all required, and optionally "name"}]. "setups": [{"id",
        "orientation": +Z or -Z, "origin", "operations": [{"op": face, profile,
        pocket, adaptive or drill, "tool", "faces", ...}]}]. Face refs are the
        ones ``cadgen cam features`` prints; a profile with "side": "inside" names
        the walls it runs along. Every key set is closed: a key or value the job
        cannot take is refused with the ones it can.
    occurrence: which part occurrence to machine (``kit/arm``, ``pin.2``) when the
        document is an assembly. Omitted, the document must hold one part.
    out_dir: where the result GLB and the posted files go. Omitted, they go beside
        the document, as ``<stem>.cam.glb`` and ``<stem>.<setup><ext>`` (``bracket.top.nc``).
    verbose: show each stage and its time on stderr.
    """
    from cadgen._internal.cam.run import plan_job

    return plan_job(Path(target), job=job, occurrence=occurrence,
                    out_dir=None if out_dir is None else Path(out_dir), verbose=verbose)
