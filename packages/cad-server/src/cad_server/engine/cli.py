"""The engine's verbs as commands -- a thin argparse over the functions of ``api`` -- and
ordinary Python scripts call decorated models explicitly.

    python SCRIPT.py                                 the models the script explicitly calls
    cad export SRC DST [DST ...] [--json]
    cad snapshot SRC OUT.png [--display MODE|exploded=A|JSON] [--camera PRESET|az:el|JSON|authored] [--grid]
        [--pose NAME|JSON] [--annotation FILE] [--measurements FILE] [--width N] [--height N]
        [--size-profile P] [--json]
    cad serve DOC [--port N]
    cad status [--json] | stop [--json] | server [--port N] [--rotate-token]
    cad delete DOC [DOC ...] [--json]             documents deleted: record, cached document, the engine's copy
    cad inspect DOC [REF] [--query Q] [--json]      what a document holds and its build closure, or what a ref names (``refs``)

SRC and DOC are an on-disk CAD file's path or a document's id (``ids``): a model's id is what
``python SCRIPT.py`` prints for it. A script is never a source: no verb imports or builds one.

The ``cad`` command runs each verb by its name (``parser_for``, ``run``); the engine's own entry,
``python -m cad_server.engine VERB ...``, takes the same verbs as subcommands (``main``). A verb's failure
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

from cad.engine import said as _said

__all__ = ["VERBS", "Failed", "answered", "build_parser", "main", "parser_for", "run",
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
                             "CAD_ENGINE_PORT, else 3245 or the port this installation rolled to); 0 takes "
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
    parser.add_argument("ref", nargs="?", help="[FILE#][OWNER/]ELEMENT or [FILE#]OWNER (cad.engine.refs): OWNER a "
                                               "part's or an assembly's label, or its occurrence path (hand/finger.2); "
                                               "ELEMENT an element name (f:..., e:..., v:...) or face N (edge, vertex). "
                                               "An element answers what the kernel measures of it, placed where its "
                                               "occurrence stands, and what made it; a part or an assembly its volume, "
                                               "mass and world bounds, a part its placement. Without it: what the document holds (its state, parts, "
                                               "bounds, volume, materials, joints, couplings, states, sequences, animations and "
                                               "declared files), then its build closure")


def _snapshot_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    from cad.engine import snapshot

    parser.usage = "%(prog)s SRC OUT.png [options] | --job PACKET [SRC] [options]"
    parser.add_argument("document", metavar="SRC", nargs="?",
                        help="a document (.xbf, .step), a mesh file (.glb, .stl, .3mf), a robot (.urdf, .sdf, .srdf), "
                             "a drawing (.dxf), or a document id (a model's, which python SCRIPT.py prints: drawn "
                             "from what the engine holds); with --job, a file drawn in place of every job's input")
    parser.add_argument("out", metavar="OUT.png", nargs="?",
                        help="the .png to write, or a folder (one that is there, or a path ending in a separator) to "
                             "write <SRC's stem>_<UTC time>.png into")
    parser.add_argument("--job", metavar="PACKET",
                        help="a Quick Edit packet (the .snapshot.json the viewer writes), a job or a list of jobs, as "
                             "JSON or a file of it: every picture its outputs name drawn, each job's view as it was -- "
                             "its camera, display, hidden and isolated parts, pose -- with the packet's ink and "
                             "dimensions, at its output settings (padding, tightFrame, transparent, renderScale, "
                             "sizeProfile); the other flags override every job")
    parser.add_argument("--display", help="a mode (solid, shaded, parts, xray, hidden-line, wireframe), exploded=AMOUNT "
                                          "(the parts moved apart, 0 to 1; with a mode: hidden-line,exploded=0.6), or "
                                          "the display JSON object (mode, grid, appearance, camera, clip, exploded, "
                                          "hidden, isolated: part refs the picture leaves out, or alone draws), or "
                                          "a JSON file of it; a drawing takes appearance alone: light or dark, as the word "
                                          "or as {\"appearance\": ...}")
    parser.add_argument("--grid", action="store_true", help="draw the measuring grid")
    parser.add_argument("--camera", help="a preset (iso, front, back, left, right, top, bottom), azimuth:elevation, "
                                         "a camera JSON object (its position, target and orthographicHalfHeight in "
                                         "the viewer's scene coordinates, as a Quick Edit packet carries them: a "
                                         "document's or a GLB's mm, a robot's m, a 3MF's unit), or authored: the "
                                         "view --annotation's ink was drawn in, from its Quick Edit packet, exactly")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--size-profile", choices=sorted(snapshot.SIZE_PROFILES))
    parser.add_argument("--pose", help="a configuration's name (a robot's SRDF group state), or joint and coupling "
                                       "values as JSON ('{\"elbow\": 45}', '{\"curl\": 0.6}'; degrees, and a slide in "
                                       "the file's unit: a document's mm, a robot's m): the mechanism posed there; as "
                                       "built without it (a robot where the viewer opens it)")
    parser.add_argument("--annotation", metavar="FILE", help="the viewer's annotation file, or the Quick Edit packet "
                                                              "(.snapshot.json) that carries it: its ink drawn over the "
                                                              "model, on the parts it was drawn on")
    parser.add_argument("--measurements", metavar="FILE", help="Measure's dimensions (a JSON list of {start, end, label, "
                                                                "color}; the points in the viewer's scene coordinates, "
                                                                "as --camera's lengths), drawn over the model")
    parser.add_argument("--json", action="store_true", help="print what was drawn and its timings as JSON")
    return parser


def _snapshot(args: argparse.Namespace, prog: str = "cad snapshot") -> int:
    """``cad snapshot``: the verb run from its parsed flags (``snapshot.snapshot`` through ``api.snapshot``); a
    failure raised as ``Failed``, which the command says (``answered``)."""
    from cad.engine import snapshot

    if args.job is not None:
        return _snapshot_job(args, prog)
    if args.document is None or args.out is None:
        raise Failed("the following arguments are required: SRC, OUT.png (or --job PACKET)", 2)
    if snapshot.by_id(args.document):
        return _snapshot_held(args, prog)
    from cad.engine import api

    try:
        # The verb as a function (``api.snapshot``), which checks the flags as ``snapshot`` does.
        report = api.snapshot(Path(args.document), args.out, display=args.display, camera=args.camera, grid=args.grid,
                              pose=args.pose, width=args.width, height=args.height,
                              size_profile=args.size_profile, annotation=args.annotation,
                              measurements=args.measurements).report
    except snapshot.SnapshotRefused as error:
        raise Failed(str(error), 2) from None
    except ConnectionError:
        raise  # the engine not reached: its one line, as every verb says it (``answered``)
    except Exception as error:  # noqa: BLE001 - a failed render is the command's answer
        raise Failed(f"{type(error).__name__}: {error}") from None
    if args.json:
        print(json.dumps(report))
    else:
        timings = report["timings"]
        print(f"wrote {_said.given(report['output'], args.out)} ({report['width']}x{report['height']}, {report['displayMode']}"
              f"{', preview' if report['preview'] else ''}) in {timings['totalMs'] / 1000:.2f}s")
    return 0


def _snapshot_held(args: argparse.Namespace, prog: str) -> int:
    """``cad snapshot ID OUT.png``: the document the engine holds of that id, drawn from the
    memory of the worker holding it (``api.snapshot``); nothing is built."""
    from cad.engine import api, snapshot

    try:
        drawn = api.snapshot(args.document, args.out, display=args.display, camera=args.camera, grid=args.grid,
                             pose=args.pose, width=args.width, height=args.height,
                             size_profile=args.size_profile, annotation=args.annotation,
                             measurements=args.measurements)
    except (snapshot.SnapshotRefused, ValueError) as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    told_state(args.document, "drawing")
    if args.json:
        print(json.dumps(drawn.report))
    else:
        report = drawn.report  # said as a file's and a job's picture are: its size, its display, Preview
        print(f"wrote {_said.given(drawn.path, args.out)} ({drawn.width}x{drawn.height}, {report['displayMode']}"
              f"{', preview' if report.get('preview') else ''}) in {report['timings']['totalMs'] / 1000:.2f}s")
    return 0


def _snapshot_job(args: argparse.Namespace, prog: str) -> int:
    """``cad snapshot --job PACKET [SRC]``: every picture the job names (``api.snapshot(job=)``),
    a line each; with ``--json``, ``{"ok": true, "pictures": [what each drew]}``."""
    import time

    from cad.engine import api, snapshot

    if args.out is not None:
        raise Failed(f"--job writes the pictures its outputs name, so it takes no OUT ({args.out})", 2)
    started = time.perf_counter()
    try:
        drawn = api.snapshot(args.document, job=args.job, display=args.display, camera=args.camera, grid=args.grid,
                                 pose=args.pose, width=args.width, height=args.height,
                                 size_profile=args.size_profile, annotation=args.annotation,
                                 measurements=args.measurements)
    except snapshot.SnapshotRefused as error:
        raise Failed(str(error), 2) from None
    except Exception as error:  # noqa: BLE001 - a failed render is the command's answer
        raise Failed(f"{type(error).__name__}: {error}") from None
    if args.json:
        print(json.dumps({"ok": True, "pictures": [picture.report for picture in drawn],
                          "timings": {"totalMs": round((time.perf_counter() - started) * 1000)}}))
    else:
        for picture in drawn:
            report = picture.report
            print(f"wrote {os.fspath(picture.path)} ({report['width']}x{report['height']}, {report['displayMode']}"
                  f"{', preview' if report['preview'] else ''}) in {report['timings']['totalMs'] / 1000:.2f}s")
    return 0


def build_parser(prog: str = "python -m cad_server.engine") -> argparse.ArgumentParser:
    """The engine's own command: its verbs as subcommands, each with its options."""
    parser = argparse.ArgumentParser(prog=prog, description="Export, draw and serve the engine's documents.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb, (help_text, arguments, _runner) in VERBS.items():
        arguments(verbs.add_parser(verb, help=help_text, description=help_text))
    return parser


def parser_for(verb: str, prog: str | None = None) -> argparse.ArgumentParser:
    """One verb's parser, as a command of its own (``cad export``, ``cad snapshot``, ...)."""
    help_text, arguments, _runner = VERBS[verb]
    parser = argparse.ArgumentParser(prog=prog or f"cad {verb}", description=help_text)
    arguments(parser)
    return parser


def run(verb: str, argv: list[str] | None = None, prog: str | None = None) -> int:
    """One verb run as a command of its own: its arguments parsed by ``parser_for``."""
    prog = prog or f"cad {verb}"
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
    from cad.engine import client

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


def told_state(source: Any, doing: str) -> None:
    """A model document read by its id, said once on stderr once a verb has read it, when its last
    run failed, so the previous good build is read: from what the engine reports of it
    (``model_info``). The verb goes on: a notice, never a refusal, and nothing reruns."""
    from cad.engine.ids import is_id

    ident = os.fspath(source).partition("#")[0]
    if not is_id(ident):
        return
    from cad.engine.client import request

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
    from cad.engine.records import rerun

    name = (model.get("source") or {}).get("name") or model.get("id")
    if model.get("state") == "failed":
        program = (model.get("source") or {}).get("script")  # the script that defines it, never a caller
        fix = f"; fix it and run `{rerun(program)}` to update it" if program else ""
        return f"the last run of {name} failed; {doing} its previous good build{fix}"
    return None


def _export(args: argparse.Namespace, prog: str) -> int:
    """``cad export SRC DST...``: an ``.xbf``, a ``.step``, a document id or a mesh file written
    to each destination (``api.export`` refuses any other source); with ``--json``, what was written
    as one JSON object."""
    from cad.engine import api
    from cad.engine.addresses import key
    from cad.engine.export import ExportRefused

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
    _said.written(written, args.destinations)
    return 0


def _serve(args: argparse.Namespace, prog: str) -> int:
    from cad.engine import api

    try:
        print(api.serve(args.document, args.port).url)
    except ValueError as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    return 0


def inspect_parser(prog: str = "cad inspect") -> argparse.ArgumentParser:
    """``cad inspect``'s parser: a document, and a ref into it or none."""
    return parser_for("inspect", prog)


def inspect_main(argv: list[str] | None = None, prog: str = "cad inspect") -> int:
    """``cad inspect DOC``: the build closure the xbf holds; ``cad inspect DOC REF``: what the
    kernel measures of the elements a ref names, and what made each (``made_by``, null for a model's
    document no live worker built; none of a file, which names no model)."""
    return run("inspect", argv, prog)


def _inspect(args: argparse.Namespace, prog: str) -> int:
    from cad.engine import api

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
        rows = [plain(f"{row['name']}  {_said.number(row['duration'])} s") for row in mesh["animations"]]
        print("animations" + "".join(f"\n  {row}" for row in rows) if rows else "animations  none")
        print("closure     none: a mesh carries none, only an .xbf does")
    elif query in ("summary", "structure") and not args.json:
        print(summary_text(found["summary"]))
        path = Path(str(found["summary"]["state"].get("path") or ""))
        if found["closure"] is None and path.suffix.lower() in (".step", ".stp"):
            print("closure     none: a STEP file carries none, only an .xbf does (a model's document, inspected by its "
                  "id, has one)")
        elif found["closure"] is None:
            print("closure     none: no build of text-to-cad's wrote this document")
        else:
            print("closure")
            print(json.dumps(found["closure"], indent=2))
    else:
        print(json.dumps(found, indent=2))
    return 0


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
    """``cad inspect DOC``'s first screen (``api._summary``): a line per fact the document
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
            size = " x ".join(_said.number(value) for value in bounds["size"])
            corner = ", ".join(_said.number(value) for value in bounds["min"])
            lines.append(f"bounds      {size} mm, from ({corner})")
        else:
            lines.append("bounds      none: no geometry")
        lines.append(f"volume      {_said.number(summary['volume'])} mm^3")
    if summary["materials"]:
        mass = summary.get("mass")
        lines.append("materials" + (f"   {_said.number(mass)} kg in all" if mass is not None else ""))
        for row in summary["materials"]:
            if not measured:
                lines.append(f"  {row['name']}: {', '.join(row['parts'])}")
                continue
            weight = f"{_said.number(row['mass'])} kg" if row["mass"] is not None else "no density"
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
            ranges.append("free" if not limits else f"{_said.number(limits[0])} to {_said.number(limits[1])} {unit}".rstrip())
        built = row.get("asBuilt")
        as_built = "" if built is None else f", as built {_joint_value(built)}"
        return f"{row['name']}  {row['type']}  {'; '.join(ranges) or 'no range'}{as_built}"

    listed("joints", [joint(row) for row in summary["joints"]])

    def coupling(row: dict[str, Any]) -> str:
        joints = ", ".join(f"{joint['name']} {_said.number(joint['ratio'])}" if isinstance(joint["ratio"], (int, float))
                           else f"{joint['name']} {' '.join(_said.number(value) for value in joint['ratio'])}"
                           for joint in row["joints"])
        ratio = f", ratio {_said.number(row['ratio'])}" if row.get("ratio") is not None else ""
        return f"{row['name']}  {row['kind']}  {joints}{ratio}"

    listed("couplings", [coupling(row) for row in summary.get("couplings") or []])
    listed("states", [f"{row['name']}  " + ", ".join(f"{name} {_joint_value(value)}" for name, value in row["values"].items())
                      for row in summary["states"]])
    listed("sequences", [f"{row['name']}  {_said.number(row['duration'])} s" for row in summary["sequences"]])
    listed("animations", [f"{row['name']}  {_said.number(row['duration'])} s" for row in summary["animations"]])
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
    from cad_server.engine.daemon import main as daemon

    if args.port is not None and not 0 <= args.port <= 65535:
        raise Failed("--port must be between 0 and 65535", 2)
    return daemon([], port=args.port, rotate=args.rotate_token, foreground=True)


def _status(args: argparse.Namespace, _prog: str) -> int:
    from cad.engine.client import request, sweep

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
    """The stale engine files a sweep removed, on stderr (stdout is the answer's)."""
    for path in swept["removed"]:
        print(f"removed stale engine file {path}", file=sys.stderr)


def _stop(args: argparse.Namespace, prog: str) -> int:
    from cad.engine.client import sweep

    # The engine, whatever release runs it; stopped means gone: the next command starts a fresh one,
    # the current installation's.
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


def delete(documents: Any) -> list[dict[str, Any]]:
    """``cad delete``: documents deleted, each by the one deletion the home's Delete is too
    (``models.delete``): what the engine holds of it, when one runs (never started for it), then its
    record and its document in the engine's cache. Each of ``documents`` is a document's id, a model's
    script or a shape's home (every document recorded of it), or a CAD file's path a page opened; the
    person's own files are never touched. One that names nothing recorded is refused (``ValueError``),
    naming each, before anything is deleted. What was deleted, ``{"id", "name", "kind"}`` each, in
    the order named."""
    from cad_server.engine import registry as registering
    from cad.engine.api import EngineError
    from cad.engine.client import request
    from cad.engine.ids import canonical, file_id, is_id
    from cad_server.engine.models import delete as deleting

    held = registering.current()
    idents: list[str] = []
    unknown: list[str] = []
    listed: list[dict[str, Any]] | None = None
    for named in [str(document) for document in documents]:
        found: list[str] = []
        if held is not None and is_id(named):
            found = [named] if held.get(named) is not None else []
        elif held is not None:
            path = canonical(os.path.abspath(os.path.expanduser(named)))
            record = held.get(file_id(path))
            if record is not None and record.get("kind") == "file":
                found = [record["id"]]
            else:
                listed = held.list() if listed is None else listed
                found = sorted(row["id"] for row in listed if row.get("kind") != "file"
                               and canonical(registering.home(held, row)) == path)
        if not found:
            unknown.append(named)
        idents.extend(ident for ident in found if ident not in idents)
    if unknown:
        raise ValueError(f"no document is recorded for {', '.join(unknown)}: name a document's id, a model's "
                         "script or a CAD file a page opened (`cad status` lists the documents); nothing "
                         "was deleted")
    answer = request({"op": "delete", "ids": idents}, start=False)
    if answer is not None:
        if not answer.get("ok"):
            raise EngineError(str(answer.get("failed") or answer.get("error") or answer))
        return list(answer.get("deleted") or [])
    return [found for found in (deleting(held, ident) for ident in idents) if found is not None]


def _delete(args: argparse.Namespace, _prog: str) -> int:
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


def main(argv: list[str] | None = None, prog: str = "python -m cad_server.engine") -> int:
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


def _gb(megabytes: Any) -> str:
    return "-" if megabytes is None else f"{float(megabytes) / 1024:.1f} GB"


def _port(serving: dict[str, Any]) -> str:
    """Where the served port came from, in words -- the default, ``--port``, ``CAD_ENGINE_PORT``
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
    return " (" + {"--port": "the port --port named", "CAD_ENGINE_PORT": "the port CAD_ENGINE_PORT names"
                   }.get(source, f"not the default {default}") + ")"


def cache_text(root: Any, documents: Any, size: Any) -> str:
    """The engine's document cache as ``cad status`` and ``cad doctor`` say it, after the word
    ``cache``: its folder, and the documents and bytes it keeps, which stay until a person deletes
    them (no cap)."""
    return (f"{root}: {documents or 0} document{'' if documents == 1 else 's'} · {_said.size(size)}, "
            "kept until deleted")


def workers_text(answer: dict[str, Any]) -> str:
    """The workers against their count cap, as ``cad status`` (and ``cad doctor``) says them:
    the standby holds a slot of the cap, counted with the workers, never one of them."""
    counted = len(answer.get("workers") or []) + (1 if answer.get("standby") else 0)
    return f"workers {counted}/{answer.get('cap')}" + (" with the standby" if answer.get("standby") else "")


def status_text(answer: dict[str, Any]) -> str:
    """``cad status``: the server and its pool's rules -- its workers against their count cap,
    their memory against its cap -- a line per worker -- busy or idle, its script, process, builds
    and memory after its last build, where a busy one's build is (its last progress frame), how long
    it has been busy or idle -- the standby's line (its process and memory: no script), the making of
    the CAD kernel environment while the engine makes it, the builds waiting for a worker, the last
    retirements, what it serves and holds under its memory budget,
    and each model document's state, with the command that builds again one not held."""
    import time

    workers = answer.get("workers") or []
    standby = answer.get("standby")
    cap = answer.get("rssCapMb")
    resident = answer.get("rssMb")
    memory = (f"RSS {_gb(resident)} of {_gb(cap)}" if resident is not None else f"RSS cap {_gb(cap)}") if cap \
        else "no RSS cap"
    version = answer.get("installation") or answer.get("version")  # the installation's: two are told apart
    lines = [" · ".join([f"engine server {answer.get('pid')}" + (f" (text-to-cad {version})" if version else "")
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
            from cad.engine.progress import describe

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
    made = answer.get("base") or {}
    if made.get("state") == "making":
        # The engine making its kernel environment (``base.Making``): the standby, and the builds, wait for it.
        lines.append(f"  base     making the CAD kernel environment · {made.get('line') or ''} · {_span(made.get('seconds'))}")
    elif made.get("state") == "failed":
        lines.append(f"  base     the CAD kernel environment was not made: {made.get('error')}")
    if answer.get("waiting"):
        waiting = answer["waiting"]
        lines.append(f"  waiting  {waiting} build{'' if waiting == 1 else 's'}, first come first served")
    retired = answer.get("retired") or []
    if retired:
        now = time.time()
        # A worker's retirement names its script; a render process's its document's renderer.
        lines.append("retired: " + " · ".join(
            (f"{Path(str(row['script'])).name}" if "script" in row else f"{Path(str(row.get('document'))).name}'s renderer")
            + f" ({row['reason']}) {_span(now - row['at'])} ago" for row in retired))
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
        # What this engine's start said: a move of its port.
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
