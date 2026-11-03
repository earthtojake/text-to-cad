"""The manufacturing check every 3D document type shares: ``cad.<type>.dfm(source, process=...)``.

``model``, ``xbf``, ``step``, ``stl``, ``threemf`` and ``glb`` each answer ``dfm`` with the same function,
made for the type here (``dfm_for``): its signature takes a file of the type (or, for ``model``, a document
the engine holds: its id or handle) and plain values alone, so it is the type's (the signature rule), and
its measuring is the trimesh integration's (``cad.trimesh._check``), imported when it runs. Two processes:

- ``molding``, injection molding: draft, undercut candidates and projected area along one pull
  (``pull``), or with ``candidates`` the pulls ranked (x, y, z and the mesh's principal axes);
- ``printing``, 3D printing: walls, overhangs and support volume, or with ``candidates`` the six
  axis-aligned orientations ranked.

Each option belongs to a process (``OPTIONS``), and one given to the other process is refused by name
before anything is read, as an option the check does not take would be (law 16). The standard library
alone: the server's command resolves the options here before it starts an environment that holds the
integration.
"""

from __future__ import annotations


from pathlib import Path
from typing import Any

from cad.results import CheckResult

__all__ = ["DEFAULTS", "OPTIONS", "PROCESSES", "UNITS_MM", "dfm_for", "options"]

#: The processes a check measures for.
PROCESSES = ("molding", "printing")
#: Length units a mesh file may carry, as a factor to millimetres. An STL is unitless, so the caller says
#: which one; the other types declare theirs.
UNITS_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
#: Each process's options and their defaults (``candidates``, the ranking, is every process's).
OPTIONS: dict[str, dict[str, Any]] = {
    "molding": {"pull": "z", "units": "mm", "wall_limit": 45.0, "zero_tol": 0.05},
    "printing": {"units": "mm", "samples": 2000, "angle_limit": 45.0},
}
DEFAULTS = {name: value for given in OPTIONS.values() for name, value in given.items()}
# The types that declare their own units, read as millimetres: a units option is the STL's alone.
_DECLARED = {"threemf": "a 3MF declares its unit", "glb": "a GLB is in glTF's metres",
             "step": "a STEP declares its units", "xbf": "an xbf is in millimetres",
             "model": "a model is in millimetres"}


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def options(document_type: str, process: str | None, given: dict[str, Any], *, candidates: bool = False) -> dict[str, Any]:
    """The options a check of ``process`` runs with: those ``given`` (None: not given), the process's
    defaults for the rest. ``ValueError`` naming the fix for no process or another, an option of the
    other process, a pull beside ``candidates`` (which ranks every pull), a units the type does not
    take, or a value out of range."""
    if process is None:
        raise ValueError(f"cad.{document_type}.dfm measures for a process: give --process "
                         f"{' or '.join(PROCESSES)}")
    if process not in PROCESSES:
        raise ValueError(f"--process is {' or '.join(PROCESSES)}, not {process!r}")
    own = OPTIONS[process]
    foreign = [name for name, value in given.items() if value is not None and name not in own]
    if foreign:
        takes = ", ".join(_flag(name) for name in (*own, "candidates"))
        raise ValueError(f"{', '.join(_flag(name) for name in foreign)} {'is' if len(foreign) == 1 else 'are'} not "
                         f"{process}'s: a {process} check takes {takes}")
    if candidates and given.get("pull") is not None:
        raise ValueError("--candidates ranks every pull: give it no --pull")
    resolved = {name: given[name] if given.get(name) is not None else default for name, default in own.items()}
    units = resolved["units"]
    if units not in UNITS_MM:
        raise ValueError(f"--units is one of {', '.join(UNITS_MM)}, not {units!r}")
    if units != "mm" and document_type in _DECLARED:
        raise ValueError(f"{_DECLARED[document_type]}, read as millimetres: --units is an STL's, which declares none")
    for name in ("wall_limit", "angle_limit"):
        if name in resolved and not 0.0 < float(resolved[name]) <= 90.0:
            raise ValueError(f"{_flag(name)} is an angle in degrees above 0 and at most 90, not {resolved[name]}")
    if "zero_tol" in resolved and not 0.0 <= float(resolved["zero_tol"]) < 90.0:
        raise ValueError(f"--zero-tol is an angle in degrees from 0 below 90, not {resolved['zero_tol']}")
    if "samples" in resolved and int(resolved["samples"]) < 1:
        raise ValueError(f"--samples is a count of at least 1, not {resolved['samples']}")
    return resolved


def dfm_for(document_type: str) -> Any:
    """``cad.<document_type>.dfm``: the manufacturing check, for a source of that type."""

    def dfm(
        source: Path,
        *,
        process: str | None = None,
        pull: str | None = None,
        units: str | None = None,
        wall_limit: float | None = None,
        zero_tol: float | None = None,
        samples: int | None = None,
        angle_limit: float | None = None,
        candidates: bool = False,
    ) -> CheckResult:
        """Measure a part for a manufacturing process: injection molding or 3D printing.

        Molding measures draft, undercut candidates and projected area along one pull; printing measures
        the mesh, overhangs, wall thickness and support volume. The figures are facts, never verdicts:
        compare them against the process's limits. The findings say what the measurements found (walls
        with no draft, undercut candidates, overhangs, units that look wrong) as warnings; a family that
        could not be measured is an error, and fails the check. --json carries every measurement.

        source: what to measure: a file of the type (an .stl, .3mf, .glb, .step or .xbf), or a model's
          document id the engine holds (cad model dfm), or the handle its call returns.
        process: molding or printing.
        pull: molding: the pull direction, an axis (z, -y) or x,y,z components; default z.
        units: the file's length units (mm, cm, m, in, ft), an STL's alone; default mm.
        wall_limit: molding: faces at or above this many degrees from the pull are not walls; default 45.
        zero_tol: molding: draft under this many degrees is zero draft; default 0.05.
        samples: printing: rays cast for the wall-thickness field; default 2000.
        angle_limit: printing: down-facing faces under this many degrees from horizontal need support; default 45.
        candidates: rank the candidates instead: molding the pulls (x, y, z and the part's principal axes),
          printing the six axis-aligned orientations.
        """
        resolved = options(document_type, process,
                           {"pull": pull, "units": units, "wall_limit": wall_limit, "zero_tol": zero_tol,
                            "samples": samples, "angle_limit": angle_limit}, candidates=candidates)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        try:
            from cad.trimesh._check import check as measured
        except ModuleNotFoundError as error:
            from cad._internal.integrations import missing

            said = missing(error)
            if said is None:
                raise
            raise ModuleNotFoundError(said, name=error.name) from None
        assert process is not None
        return measured(document_type, source, process=process, candidates=candidates, **resolved)

    dfm.__module__ = f"cad.{document_type}"
    dfm.__qualname__ = dfm.__name__ = "dfm"
    return dfm
