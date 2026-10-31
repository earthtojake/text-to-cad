"""The words a build, an export and an inspection are said in: the run line and what is under it, a
file written, a size, a measure.

A model's run says them in its own process -- ``python model.py`` reports each model its program's own call
built (``model.Model.__call__``: ``reported``), and a program's own ``export()`` each file it wrote
(``written``) -- and the ``cadgen`` command says the same words for its verbs (``cadgen.engine.cli``), so a
person reads one vocabulary whichever ran it.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

__all__ = ["describe", "files", "given", "log", "number", "reported", "shown", "size", "weighed", "written"]


def log(text: str) -> None:
    print(text, file=sys.stderr)


def shown(path: Any) -> str:
    """A path relative to the working folder, or whole where none can be: on Windows, a path on
    another drive than the folder's."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


def given(path: Any, given: Any = ()) -> str:
    """A path a ``wrote`` line names, as the command was given it: the argument that names it,
    as typed (absolute stays absolute, a relative one stays relative to the working folder);
    one no argument names, relative where it lies under the working folder and whole where it
    does not. A job's pictures are named whole: its packet, not the command, gave them."""
    for typed in [given] if isinstance(given, (str, os.PathLike)) else given:
        try:
            if os.path.realpath(os.path.expanduser(typed)) == os.path.realpath(path):
                return os.fspath(typed)
        except (TypeError, ValueError, OSError):
            continue
    text = os.fspath(path)
    try:
        relative = os.path.relpath(text)
    except ValueError:
        return text
    return text if relative == os.pardir or relative.startswith(os.pardir + os.sep) else relative


def size(count: Any) -> str:
    """A size at a glance: ``8.6 KB``, ``12.4 MB``, ``1.2 GB``."""
    count = float(count or 0)
    for unit, scale in (("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if count >= scale:
            return f"{count / scale:.1f} {unit}"
    return f"{int(count)} B"


def number(value: float) -> str:
    """A measure at a glance: four significant figures below a thousand, whole above, never an exponent."""
    return f"{value:.4g}" if abs(value) < 1000 else f"{value:,.0f}"


def files(report: dict[str, Any]) -> list[str]:
    found = []
    for path, row in (report.get("files") or {}).items():
        state = "written" if row.get("written") else "kept"
        found.append(f"{shown(path)} ({state}, {size(row.get('bytes'))})")
    return found


def describe(report: dict[str, Any], wall: float, fresh: bool | None) -> str:
    # Each child model the run ran, and the files it wrote (``child_models``).
    children = "".join(f"\n  {name}, a child{'' if row.get('ok') else ': failed'}"
                       + "".join(f"\n    {text}" for text in files(row))
                       for name, row in (report.get("child_models") or {}).items())
    if not report.get("ok"):
        refused = report.get("failedAt")  # an OCCT exception: the call the kernel refused
        return (f"failed {report.get('model')}" + (f" at {refused}: the kernel refused it" if refused else "")
                + ("; serving its previous good build" if report.get("previous") else "") + children)
    timings = report.get("timings", {})
    memo = report.get("memo", {})
    bodies = list((report.get("bodies") or {}).values())
    listed = files(report)
    worker = "" if fresh is None else (" cold" if fresh else " warm")
    if memo.get("bodies_loaded"):
        taken = (report.get("cache") or {}).get("from")
        holder = "the engine's cache" if taken == "cache" else "its document in memory"
        loaded = memo.get("bodies_loaded", 0)
        line = (f"took {report['model']}{worker} in {wall:.2f}s: {holder} holds the model's key, "
                f"{loaded} bod{'y' if loaded == 1 else 'ies'} loaded, nothing ran") + _waited(report, "took")
        line += _delta(report.get("delta"))
    else:
        counted = {status: bodies.count(status) for status in ("run", "replayed") if bodies.count(status)}
        ran = ", ".join(f"{count} {status}" for status, count in counted.items()) or "none"
        stages = ", ".join(f"{name} {timings[name]:.2f}s" for name in ("body", "names", "document", "xbf", "step",
                                                                        "glb", "stl", "threemf", "dxf")
                           if timings.get(name))
        misses, hits = memo.get("misses", 0), memo.get("hits", 0)
        line = (f"built {report['model']}{worker} in {wall:.2f}s: bodies {ran}; {misses} miss{'' if misses == 1 else 'es'}, "
                f"{hits} hit{'' if hits == 1 else 's'}" + (f"; {stages}" if stages else ""))
        line += _waited(report, "replayed" if counted.get("replayed") and not counted.get("run") else "ran after")
        line += _delta(report.get("delta"))
        if (report.get("cache") or {}).get("changed"):
            line += f"\n  rebuilt: {report['cache']['reason']}"
    if report.get("retired"):
        listed.append(f"retired: {report['retired']}")
    return (line + "".join(f"\n  {text}" for text in listed) + children
            + "".join(f"\n  warning: kinematics: {text}" for text in report.get("kinematics", {}).get("warnings", ()))
            + _verified(report.get("verify")))


def _waited(report: dict[str, Any], how: str) -> str:
    """The end of the run line of a build that waited for its script's running one (``waited``,
    ``Daemon.behind``): what it did with what that build left, ``how`` (``took``, ``replayed``,
    ``ran after``) the build of which script, waited how long for. Nothing for one that did not wait."""
    waited = report.get("waited")
    if not waited:
        return ""
    return f"; {how} the build of {waited.get('script')} it waited {waited.get('seconds', 0):.0f}s for"


def _delta(found: dict[str, Any] | None) -> str:
    """The line under the run line: the model's parts, bounds, joints, configuration sequences and
    warnings, each with what it was where the build before it held another (``delta.delta``,
    the engine's); warnings only where there are or were some; then how many parts' geometry
    changed (``changed N``), or ``materials changed`` when only colours or materials did, so an
    edit that keeps the bounds is still seen. Nothing without one."""
    if not found:
        return ""
    times, dot = " × ", " · "
    try:  # a stdout that cannot write them (a Windows pipe in another code page) is given ASCII
        (times + dot).encode(getattr(sys.stdout, "encoding", None) or "utf-8")
    except (UnicodeEncodeError, LookupError):
        times, dot = " x ", " | "

    def axes(value: Any) -> str:
        return times.join(number(axis) for axis in value) if value else "none"

    said = []
    for name in ("parts", "bounds", "joints", "sequences", "warnings"):
        row = found.get(name) or {}
        now, changed = row.get("now"), "was" in row
        if name == "warnings" and not now and not row.get("was"):
            continue
        if name == "bounds":
            text = f"bounds {axes(now)}" + (" mm" if now else "") + (f" (was {axes(row['was'])})" if changed else "")
        elif name == "warnings":
            text = f"warnings {now}" + (f" (was {row['was']})" if changed else "")
        else:
            text = f"{name} {now}" + (f" ({now - (row['was'] or 0):+d})" if changed else "")
        said.append(text)
    changed = found.get("changed") or {}
    if changed.get("parts"):
        said.append(f"changed {changed['parts']}")
    elif changed.get("looks"):
        said.append("materials changed")
    return "\n  " + dot.join(said)


def _verified(found: dict[str, Any] | None) -> str:
    if found is None:
        return ""
    lines = [f"\n  verify: {len(found['checked'])} replayable bodies run again, {len(found['mismatches'])} differ"]
    lines += [f"\n    {name}: {found['checked'][name]}; it now runs on every build" for name in found["mismatches"]]
    return "".join(lines)


def reported(reports: list[dict[str, Any]], wall: float, fresh: bool | None, as_json: bool) -> int:
    """Each report on stdout, described or as JSON; a failed one's error and the line naming it on
    stderr, and nothing more of it; 1 if any failed."""
    failed = False
    for report in reports:
        if as_json:
            print(json.dumps({**report, "wall": round(wall, 4)}))
        elif not report.get("ok"):
            # The model's frames, once, then the line that names what failed: nothing else.
            failed = True
            sys.stdout.flush()
            print(report.get("error", ""), file=sys.stderr)
            print(describe(report, wall, fresh), file=sys.stderr)
            continue
        else:
            print(describe(report, wall, fresh))
            if report.get("profile"):
                from cadgen.engine.profiling import describe as profiled

                print(profiled(report["profile"]))
            if report.get("id"):
                print(f"  id: {report['id']}")
            if report.get("url"):
                # Only a build the engine holds has a page to open: a daemon=False
                # build's document went with its process.
                print(f"  view: {report['url']}")
        if not report.get("ok"):
            failed = True
            print(report.get("error", ""), file=sys.stderr)
    # The call's answer is read now, its page opened from its `view:` line: a pipe (an agent's shell)
    # would hold it until the script exits, after whatever the script does next -- a self-check that
    # loads the CAD kernel here takes seconds.
    sys.stdout.flush()
    return 1 if failed else 0


def written(rows: Any, typed: Any) -> None:
    """A line on stdout per file an export wrote or found holding its bytes already (``rows``), each
    named as ``typed`` names it (``given``): ``cadgen export``'s, and a program's own ``export()`` call's."""
    for row in rows:
        if row.written:
            print(f"wrote {given(row.path, typed)} ({size(row.bytes)}) in {row.seconds:.2f}s")
        else:
            print(f"unchanged {given(row.path, typed)} ({size(row.bytes)}): it holds these bytes already")


def weighed(structure: dict[str, Any], hit: Any, volumes: dict[str, float]) -> dict[str, Any]:
    """What the occurrence a ref names (``refs.Hit``, from ``refs.resolve_structure``) weighs: each
    part below it, its instance's volume (its prototype's, mm^3, by key in ``volumes``) times its
    material's density, in kg, summed; ``mass`` None when no part of it has a material with a
    density, and the parts that have none listed by their occurrence paths."""
    from cadgen.engine.refs import path_text

    prototypes = structure["prototypes"]
    total_volume = 0.0
    mass = 0.0
    weighed_any = False
    unweighed = []
    held = [(structure["instances"][node.payload["instance"]], path_text(hit.root, node)) for node in hit.node.parts()]
    for instance, path in held:
        prototype = prototypes[instance["prototype"]]
        volume = volumes[prototype["key"]]
        total_volume += volume
        density = ((prototype.get("material") or {}).get("material") or {}).get("density")
        if density is None:
            unweighed.append(path)
            continue
        mass += volume * 1e-9 * density
        weighed_any = True
    found: dict[str, Any] = {"ref": hit.ref, "parts": len(held), "volume": total_volume,
                             "mass": mass if weighed_any else None, "unweighed": unweighed}
    if len(held) == 1:
        instance, path = held[0]
        material = (prototypes[instance["prototype"]].get("material") or {}).get("material")
        found.update(part=prototypes[instance["prototype"]]["name"], path=path,
                     material=material["name"] if material else None,
                     density=material.get("density") if material else None)
    return found
