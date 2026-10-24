"""The engine's verbs as commands -- a thin argparse over the functions of ``api`` -- and
ordinary Python scripts call decorated models explicitly.

    python SCRIPT.py                                 the models the script explicitly calls
    cadgen export SRC DST [DST ...] [--json]
    cadgen snapshot SRC OUT.png [--display MODE|exploded=A|JSON] [--camera PRESET|az:el|JSON|authored] [--grid]
        [--preview] [--pose NAME|JSON] [--annotation FILE] [--measurements FILE] [--width N] [--height N]
        [--size-profile P] [--json]
    cadgen serve DOC [--port N] [--three DIR]
    cadgen status [--json] | stop [--json] | server
    cadgen inspect DOC [REF]                           a document's build closure, or what a ref names (``refs``)

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


def _no_arguments(_parser: argparse.ArgumentParser) -> None:
    return None


def _inspect_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", choices=("closure", "geometry", "build"),
                        help="inspect closure, geometry (requires REF), or build metadata; never builds a model")
    parser.add_argument("document", help="an .xbf, a STEP, or a document id")
    parser.add_argument("ref", nargs="?", help="[FILE#][OWNER/]ELEMENT or [FILE#]OWNER (cadgen.engine.refs): OWNER a "
                                               "part's or an assembly's label, or its occurrence path (hand/finger.2); "
                                               "ELEMENT an element name (f:..., e:..., v:...) or face N (edge, vertex). "
                                               "An element answers what the kernel measures of it, placed where its "
                                               "occurrence stands, and what made it; a part or an assembly its volume "
                                               "and mass. Without it: the build closure")


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
    try:
        return runner(args, prog)
    except Failed as failure:
        if as_json:
            print(json.dumps({"ok": False, "error": str(failure)}, separators=(",", ":")))
            return 1
        print(f"{prog}: {failure}", file=sys.stderr)
        return failure.status
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


def _files(report: dict[str, Any]) -> list[str]:
    found = []
    for path, row in (report.get("files") or {}).items():
        state = "written" if row.get("written") else "kept"
        found.append(f"{_shown(path)} ({state}, {row.get('bytes', 0) / 1e6:.1f} MB)")
    return found


def _describe(report: dict[str, Any], wall: float, fresh: bool | None) -> str:
    # Each child model the run ran, and the files it wrote (``child_models``).
    children = "".join(f"\n  {name}, a child{'' if row.get('ok') else ': failed'}"
                       + "".join(f"\n    {text}" for text in _files(row))
                       for name, row in (report.get("child_models") or {}).items())
    if not report.get("ok"):
        return f"failed {report.get('model')}" + children
    timings = report.get("timings", {})
    memo = report.get("memo", {})
    bodies = list((report.get("bodies") or {}).values())
    files = _files(report)
    worker = "" if fresh is None else (" cold" if fresh else " warm")
    if memo.get("bodies_loaded"):
        line = (f"took {report['model']}{worker} in {wall:.2f}s: its file holds the model's key, "
                f"{memo.get('bodies_loaded', 0)} bodies loaded, nothing ran")
    else:
        counted = {status: bodies.count(status) for status in ("run", "replayed") if bodies.count(status)}
        shown = ", ".join(f"{count} {status}" for status, count in counted.items()) or "none"
        stages = ", ".join(f"{name} {timings[name]:.2f}s" for name in ("body", "names", "document", "xbf", "step",
                                                                        "glb", "stl", "threemf", "dxf")
                           if timings.get(name))
        line = (f"built {report['model']}{worker} in {wall:.2f}s: bodies {shown}; {memo.get('misses', 0)} misses, "
                f"{memo.get('hits', 0)} hits" + (f"; {stages}" if stages else ""))
        if (report.get("cache") or {}).get("changed"):
            line += f"\n  rebuilt: {report['cache']['reason']}"
    if report.get("retired"):
        files.append(f"retired: {report['retired']}")
    return (line + "".join(f"\n  {text}" for text in files) + children
            + "".join(f"\n  warning: kinematics: {text}" for text in report.get("kinematics", {}).get("warnings", ()))
            + _verified(report.get("verify")))


def _verified(found: dict[str, Any] | None) -> str:
    if found is None:
        return ""
    lines = [f"\n  verify: {len(found['checked'])} replayable bodies run again, {len(found['mismatches'])} differ"]
    lines += [f"\n    {name}: {found['checked'][name]}; it now runs on every build" for name in found["mismatches"]]
    return "".join(lines)


def _reported(reports: list[dict[str, Any]], wall: float, fresh: bool | None, as_json: bool) -> int:
    """Each report on stdout, described or as JSON, a failed one's error on stderr; 1 if any failed."""
    failed = False
    for report in reports:
        if as_json:
            print(json.dumps({**report, "wall": round(wall, 4)}))
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
    return 1 if failed else 0


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
    if args.json:
        print(json.dumps({"ok": True, "source": str(key(args.source)),
                          "files": [{"path": str(row.path), "kind": row.kind, "bytes": row.bytes, "seconds": row.seconds}
                                    for row in written]}))
        return 0
    for row in written:
        print(f"wrote {_shown(row.path)} ({row.bytes / 1e6:.1f} MB) in {row.seconds:.2f}s")
    return 0


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
        density = (prototype.get("material") or {}).get("density")
        if density is None:
            unweighed.append(path)
            continue
        mass += volume * 1e-9 * density
        weighed_any = True
    found: dict[str, Any] = {"ref": hit.ref, "parts": len(held), "volume": total_volume,
                             "mass": mass if weighed_any else None, "unweighed": unweighed}
    if len(held) == 1:
        instance, path = held[0]
        material = prototypes[instance["prototype"]].get("material")
        found.update(part=prototypes[instance["prototype"]]["name"], path=path,
                     material=material["name"] if material else None,
                     density=material.get("density") if material else None)
    return found


def inspect_parser(prog: str = "cadgen inspect") -> argparse.ArgumentParser:
    """``cadgen inspect``'s parser: a document, and a ref into it or none."""
    return parser_for("inspect", prog)


def inspect_main(argv: list[str] | None = None, prog: str = "cadgen inspect") -> int:
    """``cadgen inspect DOC``: the build closure the xbf holds; ``cadgen inspect DOC REF``: what the
    kernel measures of the elements a ref names, and what made each (``made_by``, null for a
    document no live worker built)."""
    return run("inspect", argv, prog)


def _inspect(args: argparse.Namespace, prog: str) -> int:
    from cadgen.engine import api

    try:
        found = api.inspect(args.document, args.ref, query=args.query)
    except ValueError as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    print(json.dumps(found, indent=2))
    stale = found.get("stale") or ((found.get("live") or {}).get("stale")) if isinstance(found, dict) else None
    if stale:  # the last built state, said beside the answer: nothing reran
        print(stale["text"], file=sys.stderr)
    return 0


def _server(_args: argparse.Namespace, _prog: str) -> int:
    from cadgen.engine.daemon import main as daemon

    return daemon([])


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
    from cadgen.engine.daemon import socket_path, port_path, WINDOWS

    current = str(port_path() if WINDOWS else socket_path())
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


def status_text(answer: dict[str, Any]) -> str:
    """``cadgen status``: the server and its pool's rules, a line per worker -- busy or idle,
    its script, process, builds and memory after its last build, where a busy one's build is
    (its last progress frame), how long it has been busy or idle -- the builds waiting for a
    worker, the last retirements, what it serves and holds under its memory budget, and each
    model document's state, with the command that builds again one not held."""
    import time

    workers = answer.get("workers") or []
    cap = answer.get("rssCapMb")
    lines = [" · ".join([f"engine server {answer.get('pid')}, up {_span(answer.get('up'))}",
                         f"workers {len(workers)}/{answer.get('cap')}",
                         f"idle timeout {_span(answer.get('idleTimeout'))}",
                         f"RSS cap {_gb(cap)}" if cap else "no RSS cap"])]
    names = [Path(str(worker["script"])).name for worker in workers]
    width = max((len(name) for name in names), default=0)
    for worker, name in zip(workers, names):
        builds = f"{worker.get('builds', 0)} build{'' if worker.get('builds') == 1 else 's'}"
        doing = _span(worker.get("seconds"))
        frame = worker.get("progress")
        if worker.get("busy") and frame:
            from cadgen.engine.progress import describe

            # Where its build is: ``building tom.py::tom · Building geometry · 3/7 stages · 41s``.
            doing = f"building {frame.get('model')} · {describe(frame)} · {doing}"
        lines.append(f"  {'busy' if worker.get('busy') else 'idle'}  {name:<{width}}  {str(worker.get('pid')):>6}  "
                     f"{builds:>10}  {_gb(worker.get('rssMb')):>7}  {doing}")
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
        # What the server has loaded because a page or a command opened it -- not the documents the
        # engine holds, which the ``documents:`` lines list -- an evicted file's row left out.
        opened = sum(1 for row in serving.get("documents") or [] if row.get("state", "held") == "held")
        renders = len(answer.get("renders") or [])
        memory = serving.get("memory") or {}
        held = (memory.get("documents") or 0) + (memory.get("meshes") or 0)
        lines.append(f"serving {serving['url']}: {opened} document{'' if opened == 1 else 's'} opened by a page or a command"
                     + (f" · {renders} render process{'' if renders == 1 else 'es'}" if renders else "")
                     + (f" · {_gb(held / 2**20)} of {_gb(memory['budget'] / 2**20)} held" if memory.get("budget") else ""))
    cache = answer.get("cache") or {}
    if cache.get("enabled"):
        failures = cache.get("failures") or []
        lines.append(f"cache {cache.get('root')}: {cache.get('documents', 0)} document"
                     f"{'' if cache.get('documents') == 1 else 's'} · {_bytes(cache.get('bytes'))} of "
                     f"{_bytes(cache.get('capBytes'))}"
                     + (f" · {cache['evictions']} evicted" if cache.get("evictions") else "")
                     + (f" · last save failed: {failures[0]['error']}" if failures else ""))
    elif cache:
        lines.append("cache off (CADGEN_ENGINE_CACHE_GB=0)" if not cache.get("capBytes") else "cache off: no cache folder")
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
                line += f"  run `{row['rebuild']}`" + (" (kept in memory only)" if row.get("store") == "memory" else "")
            elif row.get("store") == "shape":
                line += "  a shape handed over: no script to rerun"
            lines.append(line)
    return "\n".join(lines)


# Each verb: its help, the function adding its arguments to a parser, and the function running it.
VERBS: dict[str, tuple[str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace, str], int]]] = {
    "export": ("write an .xbf or a .step to STEP, GLB, STL, 3MF, DXF or xbf files, by suffix; a GLB carries the "
               "document's motions as clips, a DXF draws a planar one", _export_arguments, _export),
    "snapshot": ("draw a document or a file the viewer opens as the CAD Viewer does, into a PNG", _snapshot_arguments,
                 _snapshot),
    "serve": ("serve a document over HTTP and print its URL", _serve_arguments, _serve),
    "inspect": ("a document's build closure (its source, modules, inputs and key), or what one thing a ref names is "
              "and what made it", _inspect_arguments, _inspect),
    "status": ("the engine server's workers, what each is building, and its served documents", _status_arguments,
               _status),
    "stop": ("stop the engine server", _stop_arguments, _stop),
    "server": ("run the engine server in this process", _no_arguments, _server),
}


if __name__ == "__main__":
    sys.exit(main())
