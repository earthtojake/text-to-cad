"""The joint stops every document type with a mechanism shares: ``cad.<type>.ranges(source)``.

``model``, ``xbf`` and ``step`` each answer ``ranges`` with the same function, made for the type here (``ranges_for``):
its signature takes a source of the type and plain values alone, so it is the type's (the signature rule), and what it
runs is the kernel's -- the document read and described as a robot (``engine.describe``) and its joints swept against
its parts' collision geometry (``engine.ranges``) -- imported when it runs. A model, which the engine holds with no
file, is exported by the engine to an ``.xbf`` in a temporary folder first, and the sweep reads that. It never writes
the model: a model is code, and the person or the agent adopts the numbers into its joints' ranges.

The answer is a check's (``cad.results.CheckResult``; ``StopsResult``, which says it as a table): a finding per joint (``joint_stops``, at the joint) saying its
stops and which two parts meet past each, every number in ``measurements["joints"]``; a joint it cannot sweep (a
cylindrical or spherical one, one whose parts have no collision geometry) a warning; a document with no joint to sweep
an error. The standard library alone at import: the server's command resolves the options here before it starts an
environment that holds the kernel.
"""

from __future__ import annotations

import math
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cad._internal.refused import ArgumentRefused
from cad.results import CheckFinding, CheckResult, _display

__all__ = ["INTEGRATION", "StopsResult", "options", "ranges_for"]

#: The integration the sweep runs with: the kernel reads and meshes the document.
INTEGRATION = "build123d"


#: What a sweep tests (``engine.ranges.GEOMETRY``), and how its summary says it.
Geometry = Literal["parts", "collision"]
_TESTED = {"parts": "parts' surfaces", "collision": "parts' collision shapes"}


def options(*, step: float, clearance: float, geometry: str = "parts") -> None:
    """Refuse a step or a clearance the sweep cannot use: each a positive finite number, the step at most 45 (degrees
    or millimetres: past it a part passes through a thin wall unseen), the clearance at most 10 mm."""
    for flag, value, most in (("--step", step, 45.0), ("--clearance", clearance, 10.0)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ArgumentRefused(f"{flag} is a positive number, not {value!r}")
        if value > most:
            raise ArgumentRefused(f"{flag} {value:g} is over {most:g}: a coarser sweep misses what it passes through")
    if geometry not in _TESTED:
        raise ArgumentRefused(f"--geometry is parts or collision, not {geometry!r}")


def ranges_for(document_type: str) -> Any:
    """``cad.<document_type>.ranges``: the joint stops, for a source of that type."""

    def ranges(source: Path, *, step: float = 1.0, clearance: float = 1.0, geometry: Geometry = "parts",
               verbose: bool = False) -> CheckResult:
        """Each joint's stops, found from the geometry: where its parts first meet another part.

        Each joint a person moves is turned (or slid) alone from the as-built pose, the joints that follow it
        with it and every other as built, a step at a time each way: a turn a full turn each way, a slide the
        document's extent. Its stop each way is where its child link meets its parent link (each with what is
        fixed to it): a stop whatever the other joints do, what its range declares. Where anything it moves
        meets another link first, in the pose the others stand in, that clash is said beside the stop. Parts
        touching already as built (a horn on its servo) meet only when their contact grows. Each joint's finding
        says its stops in degrees or millimetres around the as-built pose (and in its own values where that is
        not zero) and which two parts meet past each; a part declared collision none takes no part. The model
        is not changed: adopt the numbers into its joints' ranges. --json carries every number.

        source: the document: a .step or .xbf, or a model's document id the engine holds (cad model ranges), or
          the handle its call returns.
        step: the sweep's step: degrees for a turning joint, millimetres for a sliding one; default 1.
        clearance: how near two parts' surfaces come before they count as touching, in millimetres; default 1.
        geometry: what meets: parts, each part's own surface (the default: the physical stops), or collision, what
          each part declares a simulator collides it as (a fitted box where it declares one: the simulator's
          stops). A part declared collision none takes no part either way.
        verbose: say each joint's stops on stderr as it is swept (a joint that takes long is said as it starts and
          ends either way).
        """
        options(step=step, clearance=clearance, geometry=geometry)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        try:
            from cad.engine.describe import describe
            from cad.engine.export import Source
            from cad.engine.ranges import sweep
        except ModuleNotFoundError as error:
            _missing(error)
            raise
        started = time.perf_counter()
        with _readable(document_type, source) as (target, label):
            # A part's hulls are tested on the collision geometry alone: on the parts, a decomposed one is whole.
            description = describe(Source.read(target).view(), decompose=geometry == "collision")
        def say(line: str) -> None:
            print(f"ranges: {line}", file=sys.stderr, flush=True)

        # A long joint is said as it starts and ends whatever ``verbose`` says: a fine sweep takes minutes.
        stops = sweep(description, step=float(step), clearance=float(clearance), geometry=geometry,
                      told=say if verbose else None, progress=say)
        return _result(label or Path(target), stops, step=float(step), clearance=float(clearance), geometry=geometry,
                       seconds=time.perf_counter() - started)

    ranges.__module__ = f"cad.{document_type}"
    ranges.__qualname__ = ranges.__name__ = "ranges"
    return ranges


def _result(path: Path, stops: list[Any], *, step: float, clearance: float, geometry: str,
            seconds: float) -> CheckResult:
    import dataclasses

    findings: list[CheckFinding] = []
    joints = []
    for found in stops:
        joints.append({**dataclasses.asdict(found), "range": _own(found)})
        if not found.swept:
            findings.append(CheckFinding("warning", "not_swept", f"not swept: {found.why}", found.joint))
            continue
        findings.append(CheckFinding("info", "joint_stops", _words(found), found.joint))
    if not stops:
        findings.append(CheckFinding("error", "no_joints", "the document has no joint to sweep", None,
                                     "a joint is a model's mechanism: build123d's RevoluteJoint or LinearJoint "
                                     "connected between two parts"))
    swept = sum(1 for found in stops if found.swept)
    summary = (f"{swept} joint{'s' if swept != 1 else ''} swept against the {_TESTED[geometry]} at {step:g} deg or mm "
               f"a step, {clearance:g} mm clearance, in {seconds:.1f} s: nothing written")
    return StopsResult(ok=bool(stops), path=Path(path), findings=tuple(findings), summary=summary,
                       measurements={"joints": joints, "step": step, "clearance": clearance, "geometry": geometry})


@dataclass(frozen=True)
class StopsResult(CheckResult):
    """A sweep's answer: a check's, said as its table -- each joint's stops and its range in its own values,
    then what met past each stop -- rather than a line of a finding per joint; its JSON is a check's."""

    def human_lines(self) -> list[str]:
        joints = self.measurements.get("joints") or []
        rows = [("joint", "lower", "upper", "range")]
        for found in joints:
            if not found.get("swept", True):
                rows.append((found["joint"], "not swept", "", ""))
                continue
            unit = found.get("unit") or ""
            ends = [("clear" if value is None else f"{value:+g} {unit}") for value in (found["lower"], found["upper"])]
            low, high = found.get("range") or (None, None)
            own = ("-" if low is None else f"{low:g}") + " to " + ("-" if high is None else f"{high:g}")
            rows.append((found["joint"], *ends, f"{own} {unit}" if low is not None or high is not None else "clear"))
        lines = []
        if joints:
            widths = [max(len(row[at]) for row in rows) for at in range(3)]
            lines = ["  ".join(cell.ljust(width) for cell, width in zip(row[:3], widths)) + "  " + row[3]
                     for row in rows]
            lines = [line.rstrip() for line in lines]
        lines += [f"{finding.location}: {finding.message}" for finding in self.findings if finding.code == "joint_stops"]
        lines += [finding.human_line() for finding in self.findings if finding.code != "joint_stops"]
        if self.ok:
            lines.append(self.summary)
        else:
            lines.append(f"FAILED {_display(self.path)}: "
                         f"{sum(1 for f in self.findings if f.severity == 'error') or len(self.findings)} blocking finding(s)")
        return lines


def _own(found: Any) -> list[float | None]:
    """The stops in the joint's own values (the as-built value plus them): what its range declares."""
    return [None if value is None else round(found.as_built + value, 6) for value in (found.lower, found.upper)]


def _words(found: Any) -> str:
    def end(name: str, value: float | None, own: float | None, contact: Any, clash: Any) -> str:
        if contact is None:
            said = f"{name} clear{' over a full turn' if found.unit == 'deg' else ''}"
        else:
            own_words = f" ({own:g} in the joint's own values)" if found.as_built else ""
            said = (f"{name} {value:+g} {found.unit}{own_words}: {contact.moving} ({contact.moving_link}) meets "
                    f"{contact.still} ({contact.still_link}) at {contact.at:+g}")
        if clash is not None:
            said += (f", and before it, at {clash.at:+g} with the other joints as built, {clash.moving} "
                     f"({clash.moving_link}) meets {clash.still} ({clash.still_link})")
        return said

    lower, upper = _own(found)
    return "; ".join([end("lower", found.lower, lower, found.lower_contact, found.lower_clash),
                      end("upper", found.upper, upper, found.upper_contact, found.upper_clash)])


class _readable:
    """The file the sweep reads for ``source`` and what its result names it as: a file of its own type as it is; a
    model, exported by the engine to an ``.xbf`` in a temporary folder removed once it is read, named by its id."""

    def __init__(self, document_type: str, source: Any) -> None:
        self.document_type, self.source = document_type, source
        self.folder: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> tuple[Path, Path | None]:
        if self.document_type != "model":
            return Path(self.source).expanduser(), None
        from cad.engine.api import export

        ident = getattr(self.source, "id", None) or str(self.source)
        self.folder = tempfile.TemporaryDirectory(prefix="cad-ranges-")
        target = Path(self.folder.name) / "model.xbf"
        export(self.source, target, progress=False)
        return target, Path(str(ident))

    def __exit__(self, *_exc: object) -> None:
        if self.folder is not None:
            self.folder.cleanup()


def _missing(error: ModuleNotFoundError) -> None:
    """The kernel this process lacks, said in one line naming its extra (``cad._internal.integrations``)."""
    from cad._internal.integrations import missing

    said = missing(error)
    if said is not None:
        raise ModuleNotFoundError(said, name=error.name) from None
