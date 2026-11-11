"""The joint stops every document type with a mechanism shares: ``cad.<type>.ranges(source)``.

``model``, ``xbf`` and ``step`` each answer ``ranges`` with the same function, made for the type here (``ranges_for``):
its signature takes a source of the type and plain values alone, so it is the type's (the signature rule), and what it
runs is the kernel's -- the document read and described as a robot (``engine.describe``) and its joints swept against
its parts' surfaces (``engine.ranges``) -- imported when it runs. A model, which the engine holds with no
file, is exported by the engine to an ``.xbf`` in a temporary folder first, and the sweep reads that. It never writes
the model: a model is code, and the person or the agent adopts the numbers into its joints' ranges.

The answer is a check's (``cad.results.CheckResult``; ``StopsResult``, which says it as a table): a finding per joint (``joint_stops``, at the joint) saying its
stops and which two parts meet past each, every number in ``measurements["joints"]``; a joint it cannot sweep (a
cylindrical or spherical one, one whose parts have no surface to test) a warning; a document with no joint to sweep
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
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import CheckFinding, CheckResult, _display

__all__ = ["INTEGRATION", "StopsResult", "options", "ranges_for"]

#: The integration the sweep runs with: the kernel reads and meshes the document.
INTEGRATION = "build123d"


#: The sweep's resolution, in mm (``engine.ranges.RESOLUTION``, said here where the kernel is not imported): every
#: point of a tested surface is within it of a sample, so a clearance under it is refused.
RESOLUTION = 0.3


def options(*, step: float, clearance: float, joint: tuple[str, ...] = ()) -> None:
    """Refuse a step or a clearance the sweep cannot use: each a positive finite number, the step at most 45 (degrees
    or millimetres: past it a part passes through a thin wall unseen), the clearance at least ``RESOLUTION`` (the
    samples resolve no finer) and at most 10 mm; and a joint named by anything but a name. Which joints the
    document has is the kernel's to say (``engine.ranges.unknown``), once it is read."""
    for flag, value, most in (("--step", step, 45.0), ("--clearance", clearance, 10.0)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ArgumentRefused(f"{flag} is a positive number, not {value!r}")
        if value > most:
            raise ArgumentRefused(f"{flag} {value:g} is over {most:g}: a coarser sweep misses what it passes through")
    if clearance < RESOLUTION:
        raise ArgumentRefused(f"--clearance {clearance:g} is under the sweep's resolution, {RESOLUTION:g} mm: every "
                              "surface is sampled to within it, so a gap is measured no finer")
    for name in (joint,) if isinstance(joint, str) else joint:
        if not isinstance(name, str) or not name:
            raise ArgumentRefused(f"--joint names a joint, not {name!r}")


def ranges_for(document_type: str) -> Any:
    """``cad.<document_type>.ranges``: the joint stops, for a source of that type."""

    def ranges(source: Path, *, step: float = 1.0, clearance: float = RESOLUTION, joint: tuple[str, ...] = (),
               verbose: bool = False) -> CheckResult:
        """Each joint's stops, found from the geometry: where its parts first meet another part.

        Each joint a person moves is turned (or slid) alone from the as-built pose, the joints that follow it
        with it and every other as built, a step at a time each way: a turn a full turn each way, a slide the
        document's extent. Its stop each way is where its child link meets its parent link (each with what is
        fixed to it): a stop whatever the other joints do, what its range declares. Where anything it moves
        meets another link first, in the pose the others stand in, that clash is said beside the stop. Two parts
        meet where they come within the clearance and within half their gap as built (less the 0.3 mm the
        surfaces are sampled to), or where their contact grows by about 15 mm^2 on a surface that stops the motion:
        parts touching already as built (a horn on its servo) meet only when their contact grows there or one is
        pushed into the other (a part resting on its parent, turned into it, stops where it lies), parts near
        as built (apart, within the clearance) only where their gap halves, and each joint's finding names them with
        their gap as built and at each stop. A pair touching as built on a surface about the joint's axis (a plate
        bolted to a motor's output, the output drawn as one solid with the motor's case) turns on it: neither that
        face nor what of the output lies within its reach (a boss, a pin, a bolt's seat) stops the joint, and the
        finding says the pair (turns on). A clash (anything the joint moves meeting another link, the other joints as
        built) belongs to the drawn pose, which a simulator's contacts hold: the range is the stop. Parts drawn one inside the other (overlapping as built, a vendor's simplified parts sunk
        into each other) meet only where one is pushed deeper into the other than drawn, by 0.6 mm more: each
        joint's finding names them with the volume they share and how deep, and a stop they make lies past the
        true one by up to about that depth. A larger clearance only narrows a range. Each joint's finding says its stops in degrees
        or millimetres around the as-built pose (and in its own values where that is not zero) and which two
        parts meet past each, every part tested against every other on its own surface. The model is not
        changed: adopt the numbers into its joints' ranges. --json carries every number.

        source: the document: a .step or .xbf, or a model's document id the engine holds (cad model ranges), or
          the handle its call returns.
        step: the sweep's step: degrees for a turning joint, millimetres for a sliding one; default 1.
        clearance: how near two parts' surfaces come before they count as touching, in millimetres; default 0.3,
          the least (where they all but touch): a larger one stops each joint where its parts first come that near.
        joint: sweep this joint alone (repeat it for several); default every joint a person moves. A name the
          document has no such joint by is refused, naming its joints.
        verbose: say on stderr each step as it starts (reading the document, sampling its surfaces, each joint)
          and each joint's stops as it ends (a joint or a sampling that takes long is said either way).
        """
        joints = (joint,) if isinstance(joint, str) else tuple(joint)
        options(step=step, clearance=clearance, joint=joints)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        try:
            from cad.engine.describe import describe
            from cad.engine.export import Source
            from cad.engine.ranges import sweep, unknown
        except ModuleNotFoundError as error:
            _missing(error)
            raise
        def say(line: str) -> None:
            print(f"ranges: {line}", file=sys.stderr, flush=True)

        started = time.perf_counter()
        if verbose:
            say(f"reading {source} and meshing its parts")
        with _readable(document_type, source) as (target, label):
            description = describe(Source.read(target).view())
        try:
            unknown(description, joints)
        except ValueError as error:
            raise ArgumentRefused(f"--joint {error}") from None
        # A long joint is said as it starts and ends whatever ``verbose`` says: a fine sweep takes minutes.
        stops = sweep(description, step=float(step), clearance=float(clearance), joints=joints,
                      told=say if verbose else None, progress=say)
        return _result(label or Path(target), stops, step=float(step), clearance=float(clearance),
                       seconds=time.perf_counter() - started)

    ranges.__module__ = f"cad.{document_type}"
    ranges.__qualname__ = ranges.__name__ = "ranges"
    return ranges


def _result(path: Path, stops: list[Any], *, step: float, clearance: float, seconds: float) -> CheckResult:
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
    summary = (f"{swept} joint{'s' if swept != 1 else ''} swept against the parts' surfaces at {step:g} deg or mm "
               f"a step, {clearance:g} mm clearance, in {seconds:.1f} s: nothing written")
    return StopsResult(ok=bool(stops), path=Path(path), findings=tuple(findings), summary=summary,
                       measurements={"joints": joints, "step": step, "clearance": clearance})


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


#: Near pairs a joint's finding names; the rest are counted, and every one is in ``--json``.
NEAR_SAID = 3


def _words(found: Any) -> str:
    from cad.engine.ranges import closing, volume

    def end(name: str, value: float | None, own: float | None, contact: Any, clash: Any) -> str:
        if contact is None:
            said = f"{name} clear{' over a full turn' if found.unit == 'deg' else ''}"
        else:
            own_words = f" ({own:g} in the joint's own values)" if found.as_built else ""
            said = (f"{name} {value:+g} {found.unit}{own_words}: {contact.moving} ({contact.moving_link}) meets "
                    f"{contact.still} ({contact.still_link}) at {contact.at:+g}{closing(contact)}")
        if clash is not None:
            said += (f", {'and before it' if contact is not None else 'but'}, at {clash.at:+g} with the other joints "
                     f"as built, {clash.moving} ({clash.moving_link}) meets {clash.still} ({clash.still_link})"
                     f"{closing(clash)} (a clash of the drawn pose, which the simulator's contacts hold: the range is "
                     "the stop)")
        return said

    def gap(value: float | None, way: str) -> str | None:
        return None if value is None else f"{value:.2f} at the {way} stop"

    lower, upper = _own(found)
    said = "; ".join([end("lower", found.lower, lower, found.lower_contact, found.lower_clash),
                      end("upper", found.upper, upper, found.upper_contact, found.upper_clash)])
    near = list(getattr(found, "near", None) or ())
    if near:
        # Pairs within the clearance as built stop the joint only where their gap closes: said, so that a stop
        # near one of them reads against its gap.
        rows = []
        for pair in near[:NEAR_SAID]:
            ends = [said_ for said_ in (gap(pair.lower, "lower"), gap(pair.upper, "upper")) if said_]
            rows.append(f"{pair.moving} ({pair.moving_link}) and {pair.still} ({pair.still_link}) {pair.rest:.2f} mm"
                        + (f" ({', '.join(ends)})" if ends else ""))
        more = f" and {len(near) - NEAR_SAID} more (--json)" if len(near) > NEAR_SAID else ""
        said += f"; near as built: {'; '.join(rows)}{more}"
    overlapping = list(getattr(found, "overlapping", None) or ())
    if overlapping:
        # Pairs drawn one inside the other stop the joint only where the overlap deepens: said, with how much, so
        # that a stop past them reads as approximate by their depth.
        rows = [f"{pair.moving} ({pair.moving_link}) in {pair.still} ({pair.still_link}) by {volume(pair.volume)}, "
                f"{pair.depth:.1f} mm deep" for pair in overlapping[:NEAR_SAID]]
        more = f" and {len(overlapping) - NEAR_SAID} more (--json)" if len(overlapping) > NEAR_SAID else ""
        said += (f"; overlapping as drawn, stopping only where that deepens: {'; '.join(rows)}{more}")
    riding = list(getattr(found, "riding", None) or ())
    if riding:
        # Pairs touching on a surface the joint moves along: an output drawn as one solid with its case turns on
        # the face the next link is bolted to, which stops nothing.
        turning = found.unit == "deg"
        rows = [f"{pair.moving} ({pair.moving_link}) on {pair.still} ({pair.still_link})" for pair in riding[:NEAR_SAID]]
        more = f" and {len(riding) - NEAR_SAID} more (--json)" if len(riding) > NEAR_SAID else ""
        said += (f"; {'turns' if turning else 'slides'} on: {'; '.join(rows)}{more}, touching as built on a surface "
                 + ("about its axis (an output, a horn or a bearing, drawn as one solid with its case or apart)"
                    if turning else "along it (a rail, a guide)") + ": contact there stops nothing")
    return said


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
