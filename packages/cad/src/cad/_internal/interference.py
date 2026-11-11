"""The interference check a B-rep type shares (``cad.model.interference``, ``cad.xbf.interference``,
``cad.step.interference``): which parts of a document share volume.

The engine measures it, in one of its checks processes (``cad.engine.api.check``, by
``cad.build123d._interference``, whose docstring is the mechanism): every pair of parts whose boxes meet, as
built and at each stance asked -- ruled out where the two parts' meshes show air between them, else measured
exactly on the parts' own solids, and each answer kept by the two geometries, so the next check measures only
what changed. This module is the caller's side, the
standard library alone, so a command with no kernel asks it too: ``options`` makes what was asked plain data
and refuses what is no option before anything is read, ``finish`` makes the engine's report the check's
result (``cad.results.CheckResult``), and ``interference_for`` is each type's function.

The result is ``ok`` (no two parts share volume but the fits named on purpose, and every pair whose boxes met
was measured), ``failed`` (a pair does: an ``interference`` finding each, an error) or ``not_checked`` (none
was found to, but a pair could not be measured -- an ``unmeasured`` finding each -- so the document is not
shown clear; its ``reason`` is ``unmeasured``). A named fit that shares volume is an ``info`` finding
(``fit``). ``measurements`` is the report whole: ``stances``, ``pairs``, and every row of
``interferences``, ``fits`` and ``unmeasured``; ``pairs`` says how the pairs whose boxes met were answered
(``apart`` by their meshes, ``kept`` from an earlier check, ``measured`` by the kernel now) and ``slowest`` the
measurements that took longest.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused

__all__ = ["finish", "interference_for", "options"]

SAMPLES = 12
PAIR_SECONDS = 300.0
SECONDS = 1200.0
# The findings of each kind a result lists before it counts the rest (``measurements`` has every row).
_ROWS = 40
# Each finding's code, and the list of ``measurements`` that holds every row of its kind.
_LISTS = {"interference": "interferences", "unmeasured": "unmeasured", "fit": "fits"}


def _number(value: Any, name: str, *, least: float, whole: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < least:
        raise ArgumentRefused(f"{name} is a number of {least:g} or more, not {value!r}")
    if whole and int(value) != value:
        raise ArgumentRefused(f"{name} is a whole number, not {value!r}")
    return float(value)


def options(*, poses: Any = (), states: bool = False, motions: Any = (), samples: Any = None, fits: Any = (),
            jobs: Any = None, pair_seconds: Any = None, seconds: Any = None, min_volume: Any = None) -> dict[str, Any]:
    """What an interference check was asked, as the plain data the engine measures by and keeps its
    result under; anything that is no option is refused by name (an ``ArgumentRefused``, a ``ValueError``).

    ``poses``: each a mechanism state's name or ``{joint or coupling: value}`` (a JSON object's text
    is read as one); ``states``: every mechanism state too. ``motions``: configuration sequences by
    name, or ``"all"``; ``samples``: the stances taken of each, its two ends among them. ``fits``:
    the pairs meant to share volume, each two refs or globs (``("pin", "base")``, ``"bearing*,housing"``).
    ``jobs``: the processes that measure (by default one a core, four at most); ``pair_seconds``:
    how long one pair may take before it is stopped and reported unmeasured; ``seconds``: how long the
    whole check may, the pairs not reached then unmeasured; ``min_volume``: a shared volume (mm3) at or
    below it is none."""
    found_poses: list[Any] = []
    for pose in ([poses] if isinstance(poses, (str, dict)) else list(poses or ())):
        if isinstance(pose, str) and pose.lstrip().startswith("{"):
            try:
                pose = json.loads(pose)
            except ValueError as error:
                raise ArgumentRefused(f"pose {pose!r} is not a JSON object: {error}") from None
        if isinstance(pose, dict):
            if not pose or not all(isinstance(key, str) for key in pose):
                raise ArgumentRefused(f"a pose's table is {{joint or coupling: value}}, not {pose!r}")
        elif not isinstance(pose, str) or not pose.strip():
            raise ArgumentRefused(f"a pose is a mechanism state's name or {{joint: value}}, not {pose!r}")
        found_poses.append(pose)
    if motions == "all" or motions is True:
        found_motions: Any = "all"
    else:
        found_motions = [motions] if isinstance(motions, str) else list(motions or ())
        if not all(isinstance(name, str) and name.strip() for name in found_motions):
            raise ArgumentRefused(f"motions are configuration sequences' names, or \"all\", not {motions!r}")
    found_fits: list[list[str]] = []
    for fit in ([fits] if isinstance(fits, str) else list(fits or ())):
        pair = [part.strip() for part in fit.split(",")] if isinstance(fit, str) else list(fit)
        if len(pair) != 2 or not all(isinstance(part, str) and part for part in pair):
            raise ArgumentRefused(f"a fit is the two parts meant to share volume, as A,B (refs or globs), not {fit!r}")
        found_fits.append(pair)
    found: dict[str, Any] = {"poses": found_poses, "states": bool(states), "motions": found_motions, "fits": found_fits,
                             "samples": int(_number(SAMPLES if samples is None else samples, "samples", least=2, whole=True)),
                             "pair_seconds": _number(PAIR_SECONDS if pair_seconds is None else pair_seconds,
                                                     "pair_seconds", least=1),
                             "seconds": _number(SECONDS if seconds is None else seconds, "seconds", least=1),
                             "min_volume": _number(0.0 if min_volume is None else min_volume, "min_volume", least=0)}
    if jobs is not None:
        found["jobs"] = int(_number(jobs, "jobs", least=1, whole=True))
    return found


def _volume(value: float) -> str:
    return f"{value:.4g}" if abs(value) < 1000 else f"{value:,.0f}"


def _at(row: dict[str, Any]) -> str:
    more = row["stances"] - len(row["at"])
    return ", ".join(row["at"]) + (f" and {more} more" if more > 0 else "")


def _label(source: Any) -> Path:
    """What a result names its document by: a file's path, else a model's document id."""
    from cad.engine.ids import is_id

    if isinstance(source, (str, os.PathLike)) and not is_id(os.fspath(source)):
        return Path(os.fspath(source)).expanduser().resolve()
    return Path(str(getattr(source, "id", None) or source))


def finish(label: Path, checked: dict[str, Any], resolved: dict[str, Any]) -> Any:
    """The engine's answer to an interference check (``api.check``) as its result (the module's
    docstring). An option the document does not answer is raised as the command line's to fix
    (``ArgumentRefused``), as is a document that holds no B-rep."""
    from cad.results import CheckFinding, CheckResult

    if "refused" in checked:
        raise ArgumentRefused(str(checked["refused"]))
    if "unmeasured" in checked:
        raise ArgumentRefused(str(checked["unmeasured"].get("message") or "the document could not be measured"))
    report = dict(checked["measured"]["report"])
    name = report.get("name") or label.name
    findings: list[Any] = []

    def listed(rows: list[dict[str, Any]], severity: str, code: str, said: Any, value: Any, unit: str, hint: str) -> None:
        for row in rows[:_ROWS]:
            findings.append(CheckFinding(severity, code, said(row), location=row["a"], hint=hint, rule=code,
                                         value=float(value(row)), unit=unit, refs=[row["a"], row["b"]]))
        if len(rows) > _ROWS:
            findings.append(CheckFinding(severity, code, f"and {len(rows) - _ROWS:,} more pairs: measurements."
                                                         f"{_LISTS[code]} lists every one (--json)"))

    listed(report["interferences"], "error", "interference",
           lambda row: f"shares {_volume(row['volume'])} mm^3 with {row['b']} ({_at(row)})",
           lambda row: row["volume"], "mm3",
           "move or resize one of the two, or name the pair a fit if it is meant to share volume (--fit A,B)")
    listed(report["unmeasured"], "warning", "unmeasured",
           lambda row: f"not measured against {row['b']}: {row['reason']} ({_at(row)})",
           lambda row: row["stances"], "stances",
           "a pair not measured is not shown clear: give it longer (--pair-seconds, --seconds) or measure the two "
           "with overlap_volume in a check of their own")
    listed(report["fits"], "info", "fit",
           lambda row: f"shares {_volume(row['volume'])} mm^3 with {row['b']}, the fit {row['fit']} ({_at(row)})",
           lambda row: row["volume"], "mm3", "")
    pairs, stances = report["pairs"], report["stances"]
    # How each pair whose boxes met was answered: ruled out by the two surfaces, read from an earlier check's
    # measurements, or measured by the kernel now.
    how = [f"{pairs[name]:,} {said}" for name, said in (("apart", "with air between them"),
                                                         ("kept", "kept from earlier checks"),
                                                         ("measured", "measured")) if pairs.get(name)]
    looked = (f"{report['parts']} part{'' if report['parts'] == 1 else 's'} at {len(stances)} "
              f"stance{'' if len(stances) == 1 else 's'}, the boxes of {pairs['boxes_meet']:,} "
              f"pair{'' if pairs['boxes_meet'] == 1 else 's'} met{': ' + ', '.join(how) if how else ''}, "
              f"in {report['seconds']:g} s"
              + (", kept from the last check of this document" if checked.get("reused") else ""))
    shared, missed = len(report["interferences"]), len(report["unmeasured"])
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
    measurements = {**report, "asked": resolved, "measured_in": checked.get("measured_in"),
                    **({"reused": True} if checked.get("reused") else {})}
    return CheckResult(ok=status == "ok", path=label, findings=tuple(findings), summary=summary,
                       measurements=measurements, status=status, reason=reason)


def interference_for(document_type: str) -> Any:
    """``cad.<document_type>.interference``: the interference check of a model (its handle or document id),
    an ``.xbf`` or a STEP."""

    def interference(source: Any, *, poses: Any = (), states: bool = False, motions: Any = (), samples: int | None = None,
                     fits: Any = (), jobs: int | None = None, pair_seconds: float | None = None,
                     seconds: float | None = None, min_volume: float | None = None) -> Any:
        from cad._internal.document_type import refuse_other
        from cad.engine import api

        refuse_other(document_type, source)
        resolved = options(poses=poses, states=states, motions=motions, samples=samples, fits=fits, jobs=jobs,
                           pair_seconds=pair_seconds, seconds=seconds, min_volume=min_volume)
        checked = api.check(source, {"type": document_type, "process": "interference", "resolved": resolved,
                                     "candidates": False, "given": {}})
        return finish(_label(source), checked, resolved)

    interference.__name__ = interference.__qualname__ = "interference"
    interference.__module__ = f"cad.{document_type}"
    interference.__doc__ = f"""cad.{document_type}.interference: which parts of the document share volume.

Every pair of parts whose boxes meet is answered, as built and at each stance asked, in one of the engine's
checks processes: a pair whose meshes show air between the two parts shares nothing, and every other is measured
exactly by the kernel on the parts' own solids. Each answer is kept in the engine's cache by the two parts'
geometries and how one stands to the other, so a document edited is measured again only where a part that changed
is one of the two, and a check stopped by its time goes on from what it had measured. Nothing is built or
written, and the same check of an unchanged document is answered at once from the result the engine keeps: one
that answered every pair.

``poses``: mechanism states' names or ``{{joint or coupling: value}}`` tables to stand at beside as built;
``states``: every mechanism state; ``motions``: configuration sequences by name, or ``"all"``, each at
``samples`` stances (12 by default, its two ends among them). ``fits``: the pairs meant to share volume (a
press-fit pin, a bearing in its bore), each two refs or globs (``("pin", "base")``, ``"bearing*,housing"``):
listed apart, and no interference. ``jobs``: the processes that measure (one a core by default, four at
most; each holds a kernel); ``pair_seconds``: one pair's limit (300), past which it is stopped and reported
unmeasured; ``seconds``: the whole check's (1200), the pairs not reached unmeasured; ``min_volume``: a shared
volume at or below it (mm3) is none.

Returns a ``cad.results.CheckResult``: ``ok`` when no two parts share volume and every pair was measured;
``failed`` with an ``interference`` finding for each pair that does (``location`` and ``refs`` the two
occurrences' paths, ``value`` the most volume shared, mm3); ``not_checked`` (``reason``: ``unmeasured``)
when none was found but a pair could not be measured, which is never a pass. ``measurements`` holds the
stances, the pairs counted and every row. An option the document does not answer -- a pose it has no state
for, a fit that names nothing -- is refused by name (a ``ValueError``); a check that did not complete
raises as ``cad.engine.api.check`` says."""
    return interference
