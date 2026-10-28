"""The engine's verbs as commands -- a thin argparse over the functions of ``api`` -- and
ordinary Python scripts call decorated models explicitly.

    python SCRIPT.py                                 the models the script explicitly calls
    cadgen export SRC DST [DST ...] [--json]
    cadgen snapshot SRC OUT.png [--display MODE|exploded=A|JSON] [--camera PRESET|az:el|JSON|authored] [--grid]
        [--pose NAME|JSON] [--annotation FILE] [--measurements FILE] [--width N] [--height N]
        [--size-profile P] [--json]
    cadgen serve DOC [--port N] [--three DIR]
    cadgen status [--json] | stop [--json] | server [--port N] [--rotate-token]
    cadgen delete DOC [DOC ...] [--json]             documents deleted: record, cached document, the engine's copy
    cadgen inspect DOC [REF] [--query Q] [--json]      what a document holds and its build closure, or what a ref names (``refs``)

SRC and DOC are an on-disk CAD file's path or a document's id (``ids``): a model's id is what
``python SCRIPT.py`` prints for it. A script is never a source: no verb imports or builds one.

cadgen's command line runs each verb by its name (``parser_for``, ``run``); the engine's own entry,
``python -m cadgen.engine VERB ...``, takes the same verbs as subcommands (``main``). A verb's failure
is said once where its command ends (``answered``): under ``--json`` as ``{"ok": false, "error": ...}``
on stdout, exit 1; else its words on stderr, exit 2 for a request refused by name before anything ran
and 1 for one that failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

__all__ = ["VERBS", "Failed", "answered", "build_parser", "main", "parser_for", "run", "weighed",
           "inspect_main", "inspect_parser"]


def _export_arguments(export: argparse.ArgumentParser) -> None:
    export.add_argument("source", metavar="SRC", help="an .xbf, a .step, a document id (a model's, which "
                                                      "python SCRIPT.py prints), or a mesh file (.glb, .stl, "
                                                      ".3mf), which exports to the other two mesh kinds")
    export.add_argument("destinations", nargs="+", metavar="DST",
                        help=".xbf (from a STEP), .step, .glb, .stl, .3mf or .dxf (of a planar document): the "
                             "document as its code built it")
    export.add_argument("--json", action="store_true", help="print what was written as JSON")


def _serve_arguments(serve: argparse.ArgumentParser) -> None:
    serve.add_argument("document", help="an .xbf, a STEP, or a document id")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--three", help="the three.js package folder (default: the nearest node_modules/three)")


def _status_arguments(status: argparse.ArgumentParser) -> None:
    status.add_argument("--json", action="store_true", help="the server's answer as JSON")


def _stop_arguments(stop: argparse.ArgumentParser) -> None:
    stop.add_argument("--json", action="store_true", help="what was stopped as JSON")


def _delete_arguments(delete: argparse.ArgumentParser) -> None:
    delete.add_argument("documents", nargs="+", metavar="DOC",
                        help="a document's id, a model's script (every document recorded of it), or a CAD file "
                             "a page opened; your own files -- a script, its declared files, an opened file -- "
                             "are never touched")
    delete.add_argument("--json", action="store_true", help="what was deleted as JSON")


def _server_arguments(server: argparse.ArgumentParser) -> None:
    server.add_argument("--port", type=int, default=None,
                        help="the HTTP port the engine takes, refused when another process holds it (else "
                             "CADGEN_ENGINE_PORT, else 3245 or the port this installation rolled to); 0 takes "
                             "any free port")
    server.add_argument("--rotate-token", action="store_true",
                        help="replace this installation's page token first: every link shared before stops working")


def _inspect_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", choices=("summary", "structure", "closure", "geometry", "build"),
                        help="inspect a summary and the closure (the default without REF); the structure: the summary "
                             "without its bounds, volume and masses, so nothing is measured, and the closure; the "
                             "closure alone; geometry (requires REF); or build metadata. Never builds a model or "
                             "meshes a part; a part's volume and box are measured once by the engine and kept for "
                             "its geometry")
    parser.add_argument("--json", action="store_true",
                        help="without REF, the summary (or the structure) and the closure as one JSON object (a "
                             "REF's answer is JSON)")
    parser.add_argument("document", help="an .xbf, a STEP, or a document id; a GLB says its nodes, meshes and "
                                          "animations")
    parser.add_argument("ref", nargs="?", help="[FILE#][OWNER/]ELEMENT or [FILE#]OWNER (cadgen.engine.refs): OWNER a "
                                               "part's or an assembly's label, or its occurrence path (hand/finger.2); "
                                               "ELEMENT an element name (f:..., e:..., v:...) or face N (edge, vertex). "
                                               "An element answers what the kernel measures of it, placed where its "
                                               "occurrence stands, and what made it; a part or an assembly its volume, "
                                               "mass and world bounds, a part its placement. Without it: what the document holds (its state, parts, "
                                               "bounds, volume, materials, joints, couplings, states, sequences, animations and "
                                               "declared files), then its build closure")


def _snapshot_arguments(parser: argparse.ArgumentParser) -> None:
    from cadgen.engine.snapshot import _arguments

    _arguments(parser)


def _snapshot(args: argparse.Namespace, prog: str) -> int:
    from cadgen.engine.snapshot import run

    return run(args, prog)


def build_parser(prog: str = "python -m cadgen.engine") -> argparse.ArgumentParser:
    """The engine's own command: its verbs as subcommands, each with its options."""
    parser = argparse.ArgumentParser(prog=prog, description="Export, draw and serve cadgen engine documents.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb, (help_text, arguments, _runner) in VERBS.items():
        arguments(verbs.add_parser(verb, help=help_text, description=help_text))
    return parser


def parser_for(verb: str, prog: str | None = None) -> argparse.ArgumentParser:
    """One verb's parser, as a command of its own (``cadgen export``, ``cadgen snapshot``, ...)."""
    help_text, arguments, _runner = VERBS[verb]
    parser = argparse.ArgumentParser(prog=prog or f"cadgen {verb}", description=help_text)
    arguments(parser)
    return parser


def run(verb: str, argv: list[str] | None = None, prog: str | None = None) -> int:
    """One verb run as a command of its own: its arguments parsed by ``parser_for``."""
    prog = prog or f"cadgen {verb}"
    args = parser_for(verb, prog).parse_args(argv)
    return answered(VERBS[verb][2], args, prog)


class Failed(Exception):
    """A verb's failure, said once where its command ends (``answered``): its words, and the status
    the command exits with -- 2 for a request refused by name before anything ran, 1 for one that
    failed -- unless it answers in JSON."""

    def __init__(self, words: str, status: int = 1) -> None:
        super().__init__(words)
        self.status = status


def answered(runner: Callable[[argparse.Namespace, str], int], args: argparse.Namespace, prog: str) -> int:
    """A verb's run, and its failure said once: under ``--json`` as ``{"ok": false, "error": ...}``
    on stdout -- the result's channel, so a caller reading stdout always finds an answer -- and the
    status 1; else its words on stderr and its own status. A failure no verb expected is said in
    JSON too, then raised as ever (its traceback the person's, and a crash the command reports)."""
    as_json = bool(getattr(args, "json", False))
    from cadgen.engine import client

    # A verb that starts the engine says so, once, on stderr: a person can tell a fresh engine (its
    # first build cold, every document read again) from the one they had.
    client.on_started = lambda: print("engine started", file=sys.stderr, flush=True)
    try:
        return runner(args, prog)
    except (Failed, ConnectionError) as failure:
        # ``ConnectionError``: the engine not reached (none runs and none can start: a sandbox, a
        # folder refused), said in its one line, never as a crash.
        if as_json:
            print(json.dumps({"ok": False, "error": str(failure)}, separators=(",", ":")))
            return 1
        print(f"{prog}: {failure}", file=sys.stderr)
        return getattr(failure, "status", 1)
    except Exception as error:
        if as_json:
            print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}, separators=(",", ":")))
        raise


def _shown(path: Any) -> str:
    """A path relative to the working folder, or whole where none can be: on Windows, a path on
    another drive than the folder's."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


def _given(path: Any, given: Any = ()) -> str:
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


def _files(report: dict[str, Any]) -> list[str]:
    found = []
    for path, row in (report.get("files") or {}).items():
        state = "written" if row.get("written") else "kept"
        found.append(f"{_shown(path)} ({state}, {_bytes(row.get('bytes'))})")
    return found


def _describe(report: dict[str, Any], wall: float, fresh: bool | None) -> str:
    # Each child model the run ran, and the files it wrote (``child_models``).
    children = "".join(f"\n  {name}, a child{'' if row.get('ok') else ': failed'}"
                       + "".join(f"\n    {text}" for text in _files(row))
                       for name, row in (report.get("child_models") or {}).items())
    if not report.get("ok"):
        refused = report.get("failedAt")  # an OCCT exception: the call the kernel refused
        return (f"failed {report.get('model')}" + (f" at {refused}: the kernel refused it" if refused else "")
                + ("; serving its previous good build" if report.get("previous") else "") + children)
    timings = report.get("timings", {})
    memo = report.get("memo", {})
    bodies = list((report.get("bodies") or {}).values())
    files = _files(report)
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
        shown = ", ".join(f"{count} {status}" for status, count in counted.items()) or "none"
        stages = ", ".join(f"{name} {timings[name]:.2f}s" for name in ("body", "names", "document", "xbf", "step",
                                                                        "glb", "stl", "threemf", "dxf")
                           if timings.get(name))
        misses, hits = memo.get("misses", 0), memo.get("hits", 0)
        line = (f"built {report['model']}{worker} in {wall:.2f}s: bodies {shown}; {misses} miss{'' if misses == 1 else 'es'}, "
                f"{hits} hit{'' if hits == 1 else 's'}" + (f"; {stages}" if stages else ""))
        line += _waited(report, "replayed" if counted.get("replayed") and not counted.get("run") else "ran after")
        line += _delta(report.get("delta"))
        if (report.get("cache") or {}).get("changed"):
            line += f"\n  rebuilt: {report['cache']['reason']}"
    if report.get("retired"):
        files.append(f"retired: {report['retired']}")
    return (line + "".join(f"\n  {text}" for text in files) + children
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

    def size(value: Any) -> str:
        return times.join(_number(axis) for axis in value) if value else "none"

    said = []
    for name in ("parts", "bounds", "joints", "sequences", "warnings"):
        row = found.get(name) or {}
        now, changed = row.get("now"), "was" in row
        if name == "warnings" and not now and not row.get("was"):
            continue
        if name == "bounds":
            text = f"bounds {size(now)}" + (" mm" if now else "") + (f" (was {size(row['was'])})" if changed else "")
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


def _reported(reports: list[dict[str, Any]], wall: float, fresh: bool | None, as_json: bool) -> int:
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
            print(_describe(report, wall, fresh), file=sys.stderr)
            continue
        else:
            print(_describe(report, wall, fresh))
            if report.get("profile"):
                from cadgen.engine.profiling import describe

                print(describe(report["profile"]))
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


def told_state(source: Any, doing: str) -> None:
    """A model document read by its id, said once on stderr once a verb has read it, when its last
    run failed, so the previous good build is read: from what the engine reports of it
    (``model_info``). The verb goes on: a notice, never a refusal, and nothing reruns."""
    from cadgen.engine.ids import is_id

    ident = os.fspath(source).partition("#")[0]
    if not is_id(ident):
        return
    from cadgen.engine.client import request

    try:
        model = (request({"op": "model_info", "id": ident}, start=False) or {}).get("model")
    except (OSError, ValueError):
        return
    words = state_notice(model, doing) if isinstance(model, dict) else None
    if words:
        print(words, file=sys.stderr)


def state_notice(model: dict[str, Any], doing: str) -> str | None:
    """The words ``told_state`` says of a model document (``model_info``'s record), or None when its
    last run did not fail."""
    from cadgen.engine.registry import rerun

    name = (model.get("source") or {}).get("name") or model.get("id")
    if model.get("state") == "failed":
        program = (model.get("source") or {}).get("script")  # the script that defines it, never a caller
        fix = f"; fix it and run `{rerun(program)}` to update it" if program else ""
        return f"the last run of {name} failed; {doing} its previous good build{fix}"
    return None


def _log(text: str) -> None:
    print(text, file=sys.stderr)


def _export(args: argparse.Namespace, prog: str) -> int:
    """``cadgen export SRC DST...``: an ``.xbf``, a ``.step``, a document id or a mesh file written
    to each destination (``api.export`` refuses any other source); with ``--json``, what was written
    as one JSON object."""
    from cadgen.engine import api
    from cadgen.engine.addresses import key
    from cadgen.engine.export import ExportRefused

    try:
        written = api.export(args.source, *args.destinations,
                             log=lambda text: print(text, file=sys.stderr))
    except (ExportRefused, ValueError) as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    told_state(args.source, "exporting")
    if args.json:
        print(json.dumps({"ok": True, "source": str(key(args.source)),
                          "files": [{"path": str(row.path), "kind": row.kind, "bytes": row.bytes, "seconds": row.seconds,
                                     "written": row.written} for row in written]}))
        return 0
    said_written(written, args.destinations)
    return 0


def said_written(written: Any, given: Any) -> None:
    """A line on stdout per file an export wrote or found holding its bytes already, each named as
    ``given`` names it: ``cadgen export``'s, and a program's own ``export()`` call's."""
    for row in written:
        if row.written:
            print(f"wrote {_given(row.path, given)} ({_bytes(row.bytes)}) in {row.seconds:.2f}s")
        else:
            print(f"unchanged {_given(row.path, given)} ({_bytes(row.bytes)}): it holds these bytes already")


def _serve(args: argparse.Namespace, prog: str) -> int:
    from cadgen.engine import api

    try:
        print(api.serve(args.document, args.port, args.three).url)
    except ValueError as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    return 0


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


def inspect_parser(prog: str = "cadgen inspect") -> argparse.ArgumentParser:
    """``cadgen inspect``'s parser: a document, and a ref into it or none."""
    return parser_for("inspect", prog)


def inspect_main(argv: list[str] | None = None, prog: str = "cadgen inspect") -> int:
    """``cadgen inspect DOC``: the build closure the xbf holds; ``cadgen inspect DOC REF``: what the
    kernel measures of the elements a ref names, and what made each (``made_by``, null for a model's
    document no live worker built; none of a file, which names no model)."""
    return run("inspect", argv, prog)


def _inspect(args: argparse.Namespace, prog: str) -> int:
    from cadgen.engine import api

    query = args.query or (None if args.ref is not None or "#" in str(args.document) else "summary")
    try:
        found = api.inspect(args.document, args.ref, query=query)
    except ValueError as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    told_state(args.document, "inspecting")
    if "mesh" in found and not args.json:
        mesh = found["mesh"]
        print(plain(f"{mesh['name']}  a mesh (GLB)"))
        print(f"nodes       {mesh['nodes']}")
        print(f"meshes      {mesh['meshes']}")
        rows = [plain(f"{row['name']}  {_number(row['duration'])} s") for row in mesh["animations"]]
        print("animations" + "".join(f"\n  {row}" for row in rows) if rows else "animations  none")
        print("closure     none: a mesh carries none, only an .xbf does")
    elif query in ("summary", "structure") and not args.json:
        print(summary_text(found["summary"]))
        path = Path(str(found["summary"]["state"].get("path") or ""))
        if found["closure"] is None and path.suffix.lower() in (".step", ".stp"):
            print("closure     none: a STEP file carries none, only an .xbf does (a model's document, inspected by its "
                  "id, has one)")
        elif found["closure"] is None:
            print("closure     none: no cadgen build wrote this document")
        else:
            print("closure")
            print(json.dumps(found["closure"], indent=2))
    else:
        print(json.dumps(found, indent=2))
    return 0


def _number(value: float) -> str:
    """A measure at a glance: four significant figures below a thousand, whole above, never an exponent."""
    return f"{value:.4g}" if abs(value) < 1000 else f"{value:,.0f}"


# Precision::Confusion: a joint value below it is the kernel's zero, and reads as one.
_KERNEL_ZERO = 1e-7


def _joint_value(value: Any) -> str:
    """A joint's value to the viewer's Position's precision -- whole from a hundred up, one decimal
    from ten, two below -- with no trailing zeros; ``0`` below the kernel's tolerance (a placement's
    round-off, ``-2.1e-31``), and a several-valued joint's values one after another."""
    if isinstance(value, dict):
        return ", ".join(f"{name} {_joint_value(item)}" for name, item in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_joint_value(item) for item in value)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    if abs(value) < _KERNEL_ZERO:
        return "0"
    text = f"{value:.{0 if abs(value) >= 100 else 1 if abs(value) >= 10 else 2}f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


def summary_text(summary: dict[str, Any]) -> str:
    """``cadgen inspect DOC``'s first screen (``api._summary``): a line per fact the document
    holds, its lists one item per line under it; a fact it has none of says so. A structure
    (``--query structure``) has no measured line: no bounds, volume or masses."""
    import time

    lines = [f"{summary['name']}  {summary['id']}"]
    state = summary["state"]
    if state["state"] == "file":
        said = f"file {state.get('path')}"
    else:
        said = state["state"]
        if state.get("held"):
            said += f" (in {state['held']})"
        said += ", cached" if state.get("cached") else ", not cached"
        if state.get("builtAt"):
            said += f", built {_span(time.time() - state['builtAt'])} ago"
    lines.append(f"state       {said}")
    parts = summary["parts"]
    lines.append(f"parts       {parts['occurrences']} in {parts['root']}"
                 + (f" ({parts['distinct']} distinct)" if parts["distinct"] != parts["occurrences"] else ""))
    measured = "volume" in summary  # the measured lines: a structure's summary has none
    if measured:
        bounds = summary.get("bounds")
        if bounds:
            size = " x ".join(_number(value) for value in bounds["size"])
            corner = ", ".join(_number(value) for value in bounds["min"])
            lines.append(f"bounds      {size} mm, from ({corner})")
        else:
            lines.append("bounds      none: no geometry")
        lines.append(f"volume      {_number(summary['volume'])} mm^3")
    if summary["materials"]:
        mass = summary.get("mass")
        lines.append("materials" + (f"   {_number(mass)} kg in all" if mass is not None else ""))
        for row in summary["materials"]:
            if not measured:
                lines.append(f"  {row['name']}: {', '.join(row['parts'])}")
                continue
            weight = f"{_number(row['mass'])} kg" if row["mass"] is not None else "no density"
            lines.append(f"  {row['name']}: {weight}, {', '.join(row['parts'])}")
        assigned = {part for row in summary["materials"] for part in row["parts"]}
        missing = [part for part in summary["unweighed"] if part not in assigned]
        if missing:
            lines.append(f"  no material: {', '.join(missing)}")
    else:
        lines.append("materials   none set")

    def listed(title: str, rows: list[str]) -> None:
        if not rows:
            lines.append(f"{title:<11} none")
            return
        lines.append(title)
        lines.extend(f"  {row}" for row in rows)

    def joint(row: dict[str, Any]) -> str:
        units = row.get("units") or []
        ranges = []
        for at, limits in enumerate(row.get("range") or []):
            unit = units[at] if at < len(units) else ""
            ranges.append("free" if not limits else f"{_number(limits[0])} to {_number(limits[1])} {unit}".rstrip())
        built = row.get("asBuilt")
        as_built = "" if built is None else f", as built {_joint_value(built)}"
        return f"{row['name']}  {row['type']}  {'; '.join(ranges) or 'no range'}{as_built}"

    listed("joints", [joint(row) for row in summary["joints"]])

    def coupling(row: dict[str, Any]) -> str:
        joints = ", ".join(f"{joint['name']} {_number(joint['ratio'])}" if isinstance(joint["ratio"], (int, float))
                           else f"{joint['name']} {' '.join(_number(value) for value in joint['ratio'])}"
                           for joint in row["joints"])
        ratio = f", ratio {_number(row['ratio'])}" if row.get("ratio") is not None else ""
        return f"{row['name']}  {row['kind']}  {joints}{ratio}"

    listed("couplings", [coupling(row) for row in summary.get("couplings") or []])
    listed("states", [f"{row['name']}  " + ", ".join(f"{name} {_joint_value(value)}" for name, value in row["values"].items())
                      for row in summary["states"]])
    listed("sequences", [f"{row['name']}  {_number(row['duration'])} s" for row in summary["sequences"]])
    listed("animations", [f"{row['name']}  {_number(row['duration'])} s" for row in summary["animations"]])
    # The files the model's decorators declare, not what an export wrote beside it.
    listed("declared files", summary["files"])
    return "\n".join(plain(line) for line in lines)


# The control characters a name read from a file may carry (C0 but tab, DEL, C1), each shown as its
# escape: a terminal reads ESC and its kin as commands (clear the screen, write the clipboard).
_CONTROLS = {code: f"\\x{code:02x}" for code in (*range(0x00, 0x09), *range(0x0a, 0x20), *range(0x7f, 0xa0))}


def plain(text: str) -> str:
    """``text`` as a terminal may print it: names a document carries (a STEP's product, a GLB's
    node or animation, a material, a joint) are anyone's who wrote the file."""
    return text.translate(_CONTROLS)


def _server(args: argparse.Namespace, prog: str) -> int:
    from cadgen.engine.daemon import main as daemon

    if args.port is not None and not 0 <= args.port <= 65535:
        raise Failed("--port must be between 0 and 65535", 2)
    return daemon([], port=args.port, rotate=args.rotate_token, foreground=True)


def _status(args: argparse.Namespace, _prog: str) -> int:
    from cadgen.engine.client import request, sweep

    swept = sweep(stop=False)
    _told_swept(swept)
    answer = request({"op": "status"}, start=False)
    if answer is None:
        print("null" if args.json else "no engine server is running")
        return 0
    if args.json:
        print(json.dumps(answer, indent=2))
    else:
        print(status_text(answer))
    return 0


def _told_swept(swept: dict[str, list[str]]) -> None:
    """What a sweep found besides this protocol's server, on stderr (stdout is the answer's): the
    stale files it removed, and a server of an older protocol, which ``stop`` stops."""
    for path in swept["removed"]:
        print(f"removed stale engine file {path}", file=sys.stderr)
    from cadgen.engine.daemon import address

    current = str(address())
    for address in swept["running"]:
        if address != current:
            print(f"an engine server of an older cadgen runs at {address}; cadgen stop stops it", file=sys.stderr)


def _stop(args: argparse.Namespace, prog: str) -> int:
    from cadgen.engine.client import sweep

    # Every server of this installation, whatever protocol it speaks; stopped means gone: the next
    # command starts a fresh one, never reaches these.
    try:
        swept = sweep(stop=True)
    except ConnectionError as error:
        raise Failed(str(error)) from None
    _told_swept(swept)
    if args.json:
        print(json.dumps({"ok": True, "stopped": swept["stopped"]}, indent=2))
        return 0
    if not swept["stopped"]:
        print("no engine server is running")
    # A line per server stopped, for a person or an agent; JSON only under ``--json``.
    for address in swept["stopped"]:
        print(f"stopped the engine server at {address}")
    return 0


def _delete(args: argparse.Namespace, _prog: str) -> int:
    from cadgen.engine.api import delete

    try:
        deleted = delete(args.documents)
    except ValueError as error:
        raise Failed(str(error), 2) from None
    if args.json:
        print(json.dumps({"ok": True, "deleted": deleted}, indent=2))
        return 0
    # A line per document deleted, for a person or an agent; JSON only under ``--json``.
    for row in deleted:
        print(f"deleted {row['name']} {row['id']}")
    return 0


def main(argv: list[str] | None = None, prog: str = "python -m cadgen.engine") -> int:
    """The engine's own command: ``VERB [args]``, every verb of ``VERBS``."""
    args = build_parser(prog).parse_args(argv)
    return answered(VERBS[args.verb][2], args, f"{prog} {args.verb}")


def _span(seconds: Any) -> str:
    """A span of time at a glance: ``41s``, ``4m``, ``2h10m``."""
    seconds = int(max(0.0, float(seconds or 0)))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}h{minutes:02d}m" if minutes else f"{hours}h"


def _bytes(count: Any) -> str:
    """A size at a glance: ``8.6 KB``, ``12.4 MB``, ``1.2 GB``."""
    count = float(count or 0)
    for unit, scale in (("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if count >= scale:
            return f"{count / scale:.1f} {unit}"
    return f"{int(count)} B"


def _gb(megabytes: Any) -> str:
    return "-" if megabytes is None else f"{float(megabytes) / 1024:.1f} GB"


def _port(serving: dict[str, Any]) -> str:
    """Where the served port came from, in words -- the default, ``--port``, ``CADGEN_ENGINE_PORT``
    or a roll from a held default -- as the serving line's parenthesis; nothing for an answer that
    does not say."""
    port, default = serving.get("port"), serving.get("defaultPort")
    if port is None or default is None:
        return ""
    if port == default:
        return " (the default port)"
    source = serving.get("portSource") or ""
    if source == "rolled":
        return f" (rolled from {default} because {serving.get('portBecause') or 'another process'} holds it)"
    return " (" + {"--port": "the port --port named", "CADGEN_ENGINE_PORT": "the port CADGEN_ENGINE_PORT names"
                   }.get(source, f"not the default {default}") + ")"


def cache_text(root: Any, documents: Any, size: Any) -> str:
    """The engine's document cache as ``cadgen status`` and ``cadgen doctor`` say it, after the word
    ``cache``: its folder, and the documents and bytes it keeps, which stay until a person deletes
    them (no cap)."""
    return (f"{root}: {documents or 0} document{'' if documents == 1 else 's'} · {_bytes(size)}, "
            "kept until deleted")


def workers_text(answer: dict[str, Any]) -> str:
    """The workers against their count cap, as ``cadgen status`` (and ``cadgen doctor``) says them:
    the standby holds a slot of the cap, counted with the workers, never one of them."""
    counted = len(answer.get("workers") or []) + (1 if answer.get("standby") else 0)
    return f"workers {counted}/{answer.get('cap')}" + (" with the standby" if answer.get("standby") else "")


def status_text(answer: dict[str, Any]) -> str:
    """``cadgen status``: the server and its pool's rules -- its workers against their count cap,
    their memory against its cap -- a line per worker -- busy or idle, its script, process, builds
    and memory after its last build, where a busy one's build is (its last progress frame), how long
    it has been busy or idle -- the standby's line (its process and memory: no script), the builds
    waiting for a worker, the last retirements, what it serves and holds under its memory budget,
    and each model document's state, with the command that builds again one not held."""
    import time

    workers = answer.get("workers") or []
    standby = answer.get("standby")
    cap = answer.get("rssCapMb")
    resident = answer.get("rssMb")
    memory = (f"RSS {_gb(resident)} of {_gb(cap)}" if resident is not None else f"RSS cap {_gb(cap)}") if cap \
        else "no RSS cap"
    version = answer.get("installation") or answer.get("version")  # the installation's: two are told apart
    lines = [" · ".join([f"engine server {answer.get('pid')}" + (f" (cadgen {version})" if version else "")
                         + f", up {_span(answer.get('up'))}", workers_text(answer),
                         *([f"held by {answer['holders']} app server{'' if answer['holders'] == 1 else 's'}"]
                           if answer.get("holders") else []),
                         memory])]
    names = [Path(str(worker["script"])).name for worker in workers]
    width = max((len(name) for name in names), default=0)
    for worker, name in zip(workers, names):
        builds = f"{worker.get('builds', 0)} build{'' if worker.get('builds') == 1 else 's'}"
        doing = _span(worker.get("seconds"))
        frame = worker.get("progress")
        if worker.get("busy") and frame:
            from cadgen.engine.progress import describe

            # Where its request is: ``building tom.py::tom · Building geometry · 3/7 stages · 41s`` (an
            # export's or a snapshot's frame says its kind the same way: ``exporting``, ``drawing``).
            verb = {"export": "exporting", "snapshot": "drawing"}.get(str(frame.get("kind")), "building")
            doing = f"{verb} {frame.get('job')} · {describe(frame)} · {doing}"
        lines.append(f"  {'busy' if worker.get('busy') else 'idle'}  {name:<{width}}  {str(worker.get('pid')):>6}  "
                     f"{builds:>10}  {_gb(worker.get('rssMb')):>7}  {doing}")
    if standby:
        # The kernel loaded and no script: the next new script's worker.
        lines.append(f"  standby  {'':<{width}}  {str(standby.get('pid') or ''):>6}  {'':>10}  "
                     f"{_gb(standby.get('rssMb')):>7}  "
                     + ("starting" if standby.get("starting") else f"kernel loaded · {_span(standby.get('seconds'))}"))
    if answer.get("waiting"):
        waiting = answer["waiting"]
        lines.append(f"  waiting  {waiting} build{'' if waiting == 1 else 's'}, first come first served")
    retired = answer.get("retired") or []
    if retired:
        now = time.time()
        lines.append("retired: " + " · ".join(f"{Path(str(row['script'])).name} ({row['reason']}) "
                                              f"{_span(now - row['at'])} ago" for row in retired))
    serving = answer.get("serving")
    if serving:
        # What the server has loaded because a page or a command opened it -- an inspected document
        # read again after its build to measure its new parts among them (``serve.Server.measure_later``)
        # -- not the documents the engine holds, which the ``documents:`` lines list; an evicted file's
        # row left out.
        opened = sum(1 for row in serving.get("documents") or [] if row.get("state", "held") == "held")
        renders = len(answer.get("renders") or [])
        memory = serving.get("memory") or {}
        held = (memory.get("documents") or 0) + (memory.get("meshes") or 0) + (memory.get("facts") or 0)
        lines.append(f"serving {serving['url']}{_port(serving)}: {opened} document{'' if opened == 1 else 's'} opened by a page or a command"
                     + (f" · {renders} render process{'' if renders == 1 else 'es'}" if renders else "")
                     + (f" · {_gb(held / 2**20)} of {_gb(memory['budget'] / 2**20)} held" if memory.get("budget") else ""))
        # What this engine's start said: the older engines it retired, a move of its port.
        lines.extend(f"  {said}" for said in (serving.get("portNotice") or "").splitlines())
    cache = answer.get("cache") or {}
    if cache.get("enabled"):
        failures = cache.get("failures") or []
        lines.append("cache " + cache_text(cache.get("root"), cache.get("documents"), cache.get("bytes"))
                     + (f" · last save failed: {failures[0]['error']}" if failures else ""))
    elif cache:
        lines.append("cache off: no cache folder")
    identity = answer.get("identity")
    if identity:
        # What this engine's start brought to namespace/name identity (``identity.migrate``).
        skipped = identity.get("skipped") or []
        lines.append(f"identity migration at start: filled {identity.get('filled', 0)}, moved {identity.get('moved', 0)}, "
                     f"skipped {len(skipped)}" + (f" ({skipped[0]}{', ...' if len(skipped) > 1 else ''})" if skipped else ""))
    models = answer.get("models") or []
    if models:
        # Each model document, its state, and for one not held the command that builds it again.
        width = max(len(str(row.get("name"))) for row in models)
        lines.append("documents:")
        for row in models:
            line = f"  {row.get('state', ''):<8}  {str(row.get('name')):<{width}}  {row.get('id')}"
            if row.get("held"):
                line += f"  {row['held']}"  # where: memory, disk (the cache), or both
            if row.get("rebuild"):
                line += f"  run `{row['rebuild']}`"
            elif row.get("kind") == "shape":
                line += "  a shape handed over: no script to rerun"
            if row.get("state") == "failed":
                line += "  serving its previous good build"
            lines.append(line)
    return "\n".join(lines)


# Each verb: its help, the function adding its arguments to a parser, and the function running it.
VERBS: dict[str, tuple[str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace, str], int]]] = {
    "export": ("write an .xbf or a .step to STEP, GLB, STL, 3MF, DXF or xbf files, by suffix; a GLB carries the "
               "document's motions as clips, a DXF draws a planar one", _export_arguments, _export),
    "snapshot": ("draw a document or a file the viewer opens as the CAD Viewer does, into a PNG", _snapshot_arguments,
                 _snapshot),
    "serve": ("serve a document over HTTP and print its URL", _serve_arguments, _serve),
    "inspect": ("what a document holds -- its state, parts, bounds, volume, materials, joints, couplings, states, "
                "sequences, animations and declared files -- then its build closure (its source, modules, inputs "
                "and key); or what one thing a ref names is and what made it. Nothing is built or meshed",
                _inspect_arguments, _inspect),
    "status": ("the engine server's workers, what each is building, and its served documents", _status_arguments,
               _status),
    "stop": ("stop the engine server", _stop_arguments, _stop),
    "delete": ("delete documents: each one's record and its document in the engine's cache, and what the engine "
               "holds of it; never a file of yours", _delete_arguments, _delete),
    "server": ("run the engine server in this process", _server_arguments, _server),
}


if __name__ == "__main__":
    sys.exit(main())
