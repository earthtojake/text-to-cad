"""The CAM job every B-rep document type shares: ``cad.<type>.plan(source, job=..., out=...)``.

``model``, ``xbf`` and ``step`` each answer ``plan`` with the same function, made for the type here (``plan_for``):
its signature takes a source of the type and plain values alone, so it is the type's (the signature rule), and what
it runs is the integrations' -- the kernel reads the part's exact faces, FreeCAD plans and posts (``cad.freecad``) --
imported when it runs. A model, which the engine holds with no file, is written to an ``.xbf`` in a temporary folder
first, and the job reads that. One operation, one result (``cad.results.CamResult``, a check's), two uses:

- with no ``job``, what a job can name on the part, which writes nothing: its faces, holes and floors, each with
  the ref a job names it by, and its box;
- with a ``job`` (a JSON file, inline JSON or a dict) and ``out``, a folder, the plan: FreeCAD's CAM workbench plans
  each setup's toolpaths and posts them for the named controller, every path is checked against the part, and the
  results are written there (``cad._internal.cam.run``): ``result.json`` (the answer, as ``--json`` prints it),
  ``result.glb`` (the part, the stock and the toolpaths) and, when nothing is an error, the G-code for each setup.

An option of the other use is refused by name before anything is read (law 16): an ``ArgumentRefused``
(``cad._internal.refused``), which the server's command says as the command line's mistake, exit 2. The standard
library alone at import: the server's command resolves the options here before it starts the environment that
holds the kernel.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import CamResult

__all__ = ["INTEGRATION", "options", "plan_for"]

#: The integration a job runs in: the kernel reads the part, so the ``cad`` command runs a job in the installation's
#: base when its own environment lacks it (``cad_server.cli.document_types``). FreeCAD, the second, is a program the
#: person installs: its probe finds it (``cad.freecad._program``).
INTEGRATION = "build123d"


def options(*, job: Any, out: Any) -> None:
    """Refuse the options of the other use: ``out`` with no job (what a job can name writes nothing), a job with no
    ``out``, and an ``out`` that is a file (it names the folder the results go into). ``ArgumentRefused`` (a
    ``ValueError``) naming the fix."""
    if job is None:
        if out is not None:
            raise ArgumentRefused("--out is a plan's: give --job too, or nothing to list what a job can name on the "
                                  "part (its faces, holes and floors)")
        return
    if out is None:
        raise ArgumentRefused("a plan writes its results into the folder --out names: give --out DIR (any folder, a "
                              "temporary one included; it is made when missing)")
    if Path(str(out)).expanduser().is_file():
        raise ArgumentRefused(f"--out names the folder a plan writes its results into, and {out} is a file")


def plan_for(document_type: str) -> Any:
    """``cad.<document_type>.plan``: the CAM job, for a source of that type."""

    def plan(
        source: Path,
        *,
        job: str | dict | None = None,
        out: Path | None = None,
        occurrence: str | None = None,
        verbose: bool = False,
    ) -> CamResult:
        """Toolpaths and G-code for a part, planned by FreeCAD and checked against the part.

        With no job it lists what a job can name, writing nothing: every face with its ref and a machining reading
        (a flat floor at Z, a wall, a hole of a diameter and depth on an axis), the holes, the floors and the part's
        box. With a job and --out, FreeCAD's CAM workbench (FreeCAD 1.1 or newer, which the person installs:
        CAD_FREECAD names its freecadcmd, else freecadcmd on PATH, else the place its installer puts it) plans each
        setup's toolpaths and posts them for the named controller, every path is checked against the part, and its
        results are written into the folder --out names: result.json (every number, as --json prints it),
        result.glb (the part, the stock and the toolpaths, any viewer opens it) and, when nothing is an error, the
        G-code for each setup. A plan with an error fails it, its result.json and result.glb written all the same
        since they say what is wrong, and no G-code; a job that cannot run writes nothing. --json carries every
        number.

        source: the part: a .step or .xbf, or a model's document id the engine holds (cad model plan), or the
          handle its call returns.
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
        out: the folder a plan writes its results into, made when missing; the G-code in it is named
          <part>.<setup><ext> (bracket.top.nc); a job's alone.
        occurrence: which part occurrence to read (kit/arm, pin.2) when the document
          is an assembly. Omitted, the document must hold one part.
        verbose: show each stage and its time on stderr.
        """
        options(job=job, out=out)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        from cad._internal.cam.run import list_features, plan_job

        try:
            with _readable(document_type, source) as (target, label):
                if job is None:
                    return list_features(target, occurrence=occurrence, verbose=verbose, label=label)
                assert out is not None
                return plan_job(target, job=job, out=Path(out).expanduser(), occurrence=occurrence, verbose=verbose,
                                label=label)
        except ModuleNotFoundError as error:
            _missing(error)
            raise

    plan.__module__ = f"cad.{document_type}"
    plan.__qualname__ = plan.__name__ = "plan"
    return plan


class _readable:
    """The file a job reads for ``source`` and what its result names it as: a file of its own type as it is; a model,
    written to an ``.xbf`` in a temporary folder that is removed once the job is done, named by its id."""

    def __init__(self, document_type: str, source: Any) -> None:
        self.document_type, self.source = document_type, source
        self.folder: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> tuple[Path, Path | None]:
        if self.document_type != "model":
            return Path(self.source), None
        from cad.engine.api import export

        ident = getattr(self.source, "id", None) or getattr(self.source, "name", None) or str(self.source)
        self.folder = tempfile.TemporaryDirectory(prefix="cad-plan-")
        target = Path(self.folder.name) / "model.xbf"
        export(self.source, target, progress=False)
        return target, Path(str(ident))

    def __exit__(self, *_exc: object) -> None:
        if self.folder is not None:
            self.folder.cleanup()


def _missing(error: ModuleNotFoundError) -> None:
    """An integration this process lacks, said in one line naming its extra (``cad._internal.integrations``)."""
    from cad._internal.integrations import missing

    said = missing(error)
    if said is not None:
        raise ModuleNotFoundError(said, name=error.name) from None
