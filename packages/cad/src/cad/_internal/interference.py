"""The interference check a B-rep type shares (``cad.model.interference``, ``cad.xbf.interference``,
``cad.step.interference``): which parts of a document share volume.

The engine measures it, in one of its checks processes (``cad.engine.api.check``, by
``cad.build123d._interference``, whose docstring is the mechanism): every pair of parts whose boxes meet, as
built and at each pose asked -- ruled out where the two parts' meshes show air between them, else measured
exactly on the parts' own solids, and each answer kept by the two geometries, so the next check measures only
what changed. This module is the caller's side, the
standard library alone, so a command with no kernel asks it too: ``options`` makes what was asked plain data
and refuses what is no option before anything is read, ``finish`` makes the engine's report the check's
result (``cad.results.CheckResult``), and ``interference_for`` is each type's function.

The result is ``ok`` (no two parts share volume but the fits named on purpose, and every pair whose boxes met
was answered), ``failed`` (a pair does: an ``overlapping_parts`` finding each, as a stress study names the same
fact, here an error) or ``not_checked`` (none
was found to, but a pair could not be measured -- an ``unmeasured`` finding each -- so the document is not
shown clear; its ``reason`` is ``unmeasured``). A named fit that shares volume is an ``info`` finding
(``fit``). ``measurements`` is the report whole: ``poses``, ``pairs``, and every row of
``overlaps``, ``fits`` and ``unmeasured``; ``pairs`` says how the pairs whose boxes met were answered
(``apart`` by their meshes, ``kept`` from an earlier check, ``measured`` by the kernel now) and ``slowest`` the
measurements that took longest.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused

__all__ = ["finish", "interference_for", "options"]

# A shared volume at or below this is rounding along a face where two parts touch, not an overlap: the floor a
# stress study's contact search holds an overlap to (``cad._internal.fea.assembly``), in mm3.
MIN_VOLUME = 1e-3
# The findings of each kind a result lists before it counts the rest (``measurements`` has every row), and the
# poses a finding names before it counts the rest (its row has each).
_ROWS = 40
_NAMED = 4
# Each finding's code, and the list of ``measurements`` that holds every row of its kind.
_LISTS = {"overlapping_parts": "overlaps", "unmeasured": "unmeasured", "fit": "fits"}


def options(*, poses: Any = (), fits: Any = (), min_volume: Any = None) -> dict[str, Any]:
    """What an interference check was asked, as the plain data the engine measures by and keeps its
    result under; anything that is no option is refused by name (an ``ArgumentRefused``, a ``ValueError``).

    ``poses``: the poses to check at beside as built, each as every command takes a pose: a mechanism
    state's name, a configuration sequence at a time of it (``walk@0.6``), or ``{joint or coupling:
    value}``. ``fits``: the pairs meant to share volume, each two refs or globs (``("pin", "base")``).
    ``min_volume``: a shared volume (mm3) at or below it is none (``MIN_VOLUME`` by default)."""
    found_poses: list[Any] = []
    for pose in ([poses] if isinstance(poses, (str, dict)) else list(poses or ())):
        if isinstance(pose, dict):
            if not pose or not all(isinstance(key, str) for key in pose):
                raise ArgumentRefused(f"a pose's table is {{joint or coupling: value}}, not {pose!r}")
        elif not isinstance(pose, str) or not pose.strip():
            raise ArgumentRefused("a pose is a mechanism state's name, a configuration sequence at a time "
                                  f"(NAME@SECONDS) or {{joint: value}}, not {pose!r}")
        found_poses.append(pose)
    found_fits: list[list[str]] = []
    for fit in ([] if fits is None else list(fits)):
        pair = None if isinstance(fit, str) else list(fit)
        if pair is None or len(pair) != 2 or not all(isinstance(part, str) and part.strip() for part in pair):
            raise ArgumentRefused(f"a fit is the two parts meant to share volume, each a ref or a glob, not {fit!r}")
        found_fits.append([part.strip() for part in pair])
    floor = MIN_VOLUME if min_volume is None else min_volume
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not math.isfinite(floor) or floor < 0:
        raise ArgumentRefused(f"min_volume is a number of 0 or more, not {floor!r}")
    return {"poses": found_poses, "fits": found_fits, "min_volume": float(floor)}


def _volume(value: float) -> str:
    return f"{value:.4g}" if abs(value) < 1000 else f"{value:,.0f}"


def _at(row: dict[str, Any]) -> str:
    """The poses a row holds at, as a finding says them: the first few by name, and how many more."""
    more = len(row["poses"]) - _NAMED
    return ", ".join(row["poses"][:_NAMED]) + (f" and {more} more" if more > 0 else "")


def _label(source: Any) -> Path:
    """What a result names its document by: a file's path, else a model's document id."""
    from cad.engine.ids import is_id

    if isinstance(source, (str, os.PathLike)) and not is_id(os.fspath(source)):
        return Path(os.fspath(source)).expanduser().resolve()
    return Path(str(getattr(source, "id", None) or source))


def finish(label: Path, checked: dict[str, Any], resolved: dict[str, Any]) -> Any:
    """The engine's answer to an interference check (``api.check``) as its result (the module's
    docstring). An option the document does not answer is raised as the command line's to fix
    (``ArgumentRefused``); a document that does not read, or holds no B-rep, is ``not_checked`` by its
    reason, as a manufacturing check answers one (``manufacturing.not_checked``)."""
    from cad.results import CheckFinding, CheckResult

    if "refused" in checked:
        raise ArgumentRefused(str(checked["refused"]))
    if "unmeasured" in checked:
        from cad._internal.manufacturing import not_checked

        return not_checked(label, str(checked["unmeasured"].get("message") or "the document could not be measured"),
                           str(checked["unmeasured"].get("code") or "document_unreadable"))
    report = dict(checked["measured"]["report"])
    name = report.get("name") or label.name
    findings: list[Any] = []

    def listed(rows: list[dict[str, Any]], severity: str, code: str, said: Any, value: Any, unit: str, hint: str) -> None:
        for row in rows[:_ROWS]:
            first, _second = row["between"]
            findings.append(CheckFinding(severity, code, said(row), location=first, hint=hint, rule=code,
                                         value=float(value(row)), unit=unit, refs=list(row["between"])))
        if len(rows) > _ROWS:
            findings.append(CheckFinding(severity, code, f"and {len(rows) - _ROWS:,} more pairs: measurements."
                                                         f"{_LISTS[code]} lists every one (--json)"))

    listed(report["overlaps"], "error", "overlapping_parts",
           lambda row: f"shares {_volume(row['volume_mm3'])} mm^3 with {row['between'][1]} ({_at(row)})",
           lambda row: row["volume_mm3"], "mm3",
           "move or resize one of the two, or name the pair a fit if it is meant to share volume (--fit A B)")
    listed(report["unmeasured"], "warning", "unmeasured",
           lambda row: f"not measured against {row['between'][1]}: {row['message']} ({_at(row)})",
           lambda row: len(row["poses"]), "poses",
           "a pair not measured is not shown clear: ask again, which goes on from what was measured, or measure "
           "the two with overlap_volume in a check of their own")
    listed(report["fits"], "info", "fit",
           lambda row: f"shares {_volume(row['volume_mm3'])} mm^3 with {row['between'][1]}, the fit "
                       f"{' '.join(row['fit'])} ({_at(row)})",
           lambda row: row["volume_mm3"], "mm3", "")
    pairs, poses = report["pairs"], report["poses"]
    # How each pair whose boxes met was answered, by the report's own words (``pairs``): ``apart`` by the two
    # meshes, ``kept`` from an earlier check's measurements, ``measured`` by the kernel now.
    how = [f"{pairs[word]:,} {word}" for word in ("apart", "kept", "measured") if pairs.get(word)]
    looked = (f"{report['parts']} part{'' if report['parts'] == 1 else 's'} at {len(poses)} "
              f"pose{'' if len(poses) == 1 else 's'}, the boxes of {pairs['boxes_meet']:,} "
              f"pair{'' if pairs['boxes_meet'] == 1 else 's'} met{': ' + ', '.join(how) if how else ''}, "
              f"in {report['seconds']:g} s"
              + (", the result kept from the last check of this document" if checked.get("reused") else ""))
    shared, missed = len(report["overlaps"]), len(report["unmeasured"])
    if shared:
        status, reason = "failed", None
        summary = f"FAILED {name}: {shared:,} pair{'' if shared == 1 else 's'} of parts share volume ({looked})"
    elif missed:
        status, reason = "not_checked", "unmeasured"
        summary = (f"NOT CHECKED {name}: no pair measured shares volume, but {missed:,} could not be measured, so it "
                   f"is not shown clear ({looked})")
    else:
        status, reason = "ok", None
        summary = f"OK {name}: no two parts share volume ({looked})"
    measurements = {**report, "resolved": resolved, "measured_in": checked.get("measured_in"),
                    **({"reused": True} if checked.get("reused") else {})}
    return CheckResult(ok=status == "ok", path=label, findings=tuple(findings), summary=summary,
                       measurements=measurements, status=status, reason=reason)


def interference_for(document_type: str) -> Any:
    """``cad.<document_type>.interference``: the interference check of a model (its handle or document id),
    an ``.xbf`` or a STEP."""

    def interference(source: Any, *, poses: Any = (), fits: Any = (), min_volume: float | None = None) -> Any:
        from cad._internal.document_type import refuse_other
        from cad.engine import api

        refuse_other(document_type, source)
        resolved = options(poses=poses, fits=fits, min_volume=min_volume)
        checked = api.check(source, {"type": document_type, "process": "interference", "resolved": resolved,
                                     "candidates": False, "given": {}})
        return finish(_label(source), checked, resolved)

    interference.__name__ = interference.__qualname__ = "interference"
    interference.__module__ = f"cad.{document_type}"
    interference.__doc__ = f"""cad.{document_type}.interference: which parts of the document share volume.

Every pair of parts whose boxes meet is answered, as built and at each pose asked, in one of the engine's
checks processes: a pair whose meshes show air between the two parts shares nothing, and every other is measured
exactly by the kernel on the parts' own solids. Each answer is kept in the engine's cache by the two parts'
geometries and how one stands to the other, so a document edited is measured again only where a part that changed
is one of the two, and a check stopped by its time goes on from what it had measured. Nothing is built or
written, and the same check of an unchanged document is answered at once from the result the engine keeps: one
that answered every pair.

``poses``: the poses to check at beside as built, each a pose as every command takes one: a mechanism state's
name, a configuration sequence at a time of it (``"walk@0.6"``), or a ``{{joint or coupling: value}}`` table. The
check takes the poses it is given and chooses none: every state, or a sequence every tenth of a second, is the
caller's list. ``fits``: the pairs meant to share volume (a press-fit pin, a bearing in its bore), each two refs
or globs (``("pin", "base")``): listed apart, and no overlap. ``min_volume``: a shared volume at or below it
(mm3) is none; {MIN_VOLUME:g} by default, the rounding along a face where two parts touch.

Returns a ``cad.results.CheckResult``: ``ok`` when no two parts share volume and every pair was answered;
``failed`` with an ``overlapping_parts`` finding for each pair that does (``location`` and ``refs`` the two
occurrences' paths, ``value`` the most volume shared, mm3); ``not_checked`` (``reason``: ``unmeasured``)
when none was found but a pair could not be measured -- past its time, its process gone, the kernel's refusal --
which is never a pass: asked again, the check goes on from what it measured. ``measurements`` holds the poses,
the pairs counted (``pairs``: ``apart``, ``kept``, ``measured``) and every row (``overlaps``, ``fits``,
``unmeasured``: each ``between`` its two parts, with every pose it holds at). An option the document does not
answer -- a pose it has no state or sequence for, a fit that names nothing -- is refused by name (a
``ValueError``); a document that does not read is ``not_checked`` by its reason; a check that did not complete
raises as ``cad.engine.api.check`` says."""
    return interference
