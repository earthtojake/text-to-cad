"""The CAM job every B-rep document type shares: ``cad.<type>.cam(source, job=..., out=...)``.

``xbf`` and ``step`` each answer ``cam`` with the same function, made for the type here (``cam_for``): its
signature takes a file of the type and plain values alone, so it is the type's (the signature rule), and what
it runs is the integrations' -- the kernel reads the part's exact faces, FreeCAD plans and posts
(``cad.freecad``) -- imported when it runs. One operation, one result (``cad.results.CamResult``, a check's), two
uses:

- with no ``job``, what a job can name on the part, which writes nothing: its faces, holes and floors, each with
  the ref a job names it by, and its box;
- with a ``job`` (a JSON file, inline JSON or a dict) and ``out`` (the result ``.glb``), the plan: FreeCAD's CAM
  workbench plans each setup's toolpaths and posts them for the named controller, every path is checked against
  the part, and the GLB (the part, the stock and the toolpaths, with the verdict in its extras) and, when nothing
  is an error, the G-code for each setup are written, the G-code beside the GLB.

The job names a file, read here, never through the engine, so there is no decorator and ``model`` has no ``cam``. An
option of the other use is refused by name before anything is read (law 16): an ``ArgumentRefused``
(``cad._internal.refused``), which the server's command says as the command line's mistake, exit 2. The standard
library alone at import: the server's command resolves the options here before it starts the environment that
holds the kernel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import CamResult

__all__ = ["INTEGRATION", "cam_for", "options"]

#: The integration a job runs in: the kernel reads the part, so the ``cad`` command runs a job in the installation's
#: base when its own environment lacks it (``cad_server.cli.document_types``). FreeCAD, the second, is a program the
#: person installs: its probe finds it (``cad.freecad._program``).
INTEGRATION = "build123d"


def options(*, job: Any, out: Any) -> None:
    """Refuse the options of the other use: ``out`` with no job (what a job can name writes nothing), a job with no
    ``out``, and an ``out`` that is no ``.glb``. ``ArgumentRefused`` (a ``ValueError``) naming the fix."""
    if job is None:
        if out is not None:
            raise ArgumentRefused("--out is a plan's: give --job too, or nothing to list what a job can name on the "
                                  "part (its faces, holes and floors)")
        return
    if out is None:
        raise ArgumentRefused("a plan writes its result GLB where --out names it, and the G-code beside it: give "
                              "--out RESULT.cam.glb")
    if Path(str(out)).suffix.lower() != ".glb":
        raise ArgumentRefused(f"--out names the result GLB and must end in .glb, not {out}")


def cam_for(document_type: str) -> Any:
    """``cad.<document_type>.cam``: the CAM job, for a source of that type."""

    def cam(
        source: Path,
        *,
        job: str | dict | None = None,
        out: Path | None = None,
        occurrence: str | None = None,
        verbose: bool = False,
    ) -> CamResult:
        """Toolpaths and G-code for a saved part, planned by FreeCAD and checked against the part.

        With no job it lists what a job can name, writing nothing: every face with its ref and a machining reading
        (a flat floor at Z, a wall, a hole of a diameter and depth on an axis), the holes, the floors and the part's
        box. With a job and --out, FreeCAD's CAM workbench (FreeCAD 1.1 or newer, which the person installs:
        CAD_FREECAD names its freecadcmd, else freecadcmd on PATH, else the place its installer puts it) plans each
        setup's toolpaths and posts them for the named controller, and every path is checked against the part. It
        writes the result GLB the viewer draws and, when nothing is an error, the G-code for each setup beside it. A
        plan with an error fails it, its GLB written all the same since it shows what is wrong, and no G-code; a job
        that cannot run writes nothing. --json carries every number.

        source: the .step or .xbf holding the part.
        job: the job: a JSON file path, inline JSON, or (a library caller) a dict, all
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
          ones this command prints with no job; a profile with "side": "inside" names
          the walls it runs along. Every key set is closed: a key or value the job
          cannot take is refused with the ones it can. Without it, what a job can name.
        out: the result .glb a plan writes, the G-code beside it, as
          <stem>.<setup><ext> (bracket.top.nc), <stem> the part's; a job's alone.
        occurrence: which part occurrence to read (kit/arm, pin.2) when the document
          is an assembly. Omitted, the document must hold one part.
        verbose: show each stage and its time on stderr.
        """
        options(job=job, out=out)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        from cad._internal.cam.run import list_features, plan_job

        try:
            if job is None:
                return list_features(Path(source), occurrence=occurrence, verbose=verbose)
            assert out is not None
            return plan_job(Path(source), job=job, out=Path(out), occurrence=occurrence, verbose=verbose)
        except ModuleNotFoundError as error:
            _missing(error)
            raise

    cam.__module__ = f"cad.{document_type}"
    cam.__qualname__ = cam.__name__ = "cam"
    return cam


def _missing(error: ModuleNotFoundError) -> None:
    """An integration this process lacks, said in one line naming its extra (``cad._internal.integrations``)."""
    from cad._internal.integrations import missing

    said = missing(error)
    if said is not None:
        raise ModuleNotFoundError(said, name=error.name) from None
