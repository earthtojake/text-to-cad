"""``cad <document_type> <operation> <file>``: every document type's commands, from the registry.

The shape is one for every type (``cad.registry``): the type's id, then one of the fixed operations
it implements, then its file -- ``cad xbf export arm.xbf arm.step``, ``cad stl snapshot part.stl
part.png``, ``cad srdf check robot.srdf --urdf robot.urdf``. Each operation has one result shape:
``export`` says the files it wrote, ``check`` its findings (each with a severity, a code and a
location; ``--json`` the ``cad.results.CheckResult``). A type's own options live with the type.

A 3D type's ``check`` (``stl``, ``threemf``, ``glb``, ``step``, ``xbf``) is the manufacturing check, the
trimesh integration's: ``cad stl check part.stl --process molding --pull -z``, ``cad xbf check <id>
--process printing --candidates``. It runs here when this environment holds trimesh, else in the
environment the engine makes for ``cad[trimesh]`` (``cad_server._internal.integration_env``).

``cad <type> --help`` lists the type's operations, worked out from the registry, and ``cad <type>
<operation> --help`` that operation's options. A file of another type is refused by name, before
anything runs: ``part.glb is a glb, not a stl: use cad glb snapshot``.

Each type's command is its own module (``cad_server.cli.<type>``), so ``python -m
cad_server.cli.step export ...`` runs what ``cad step export ...`` does. Dispatch stays lazy: the
engine and the checks import when an operation runs, never for ``--help``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from cad.registry import DOCUMENT_TYPES, by_extension, help_text

__all__ = ["OPERATIONS", "build_parser", "operations_of", "type_main", "type_usage"]

# The engine's verbs that are operations (``cad_server.engine.cli.VERBS``), and the attribute of the
# parsed arguments each names its source by.
_ENGINE_SOURCES = {"export": "source", "snapshot": "document", "inspect": "document"}


def _urdf_parser(prog: str) -> argparse.ArgumentParser:
    """``cad urdf check``'s parser, an ADAPTER's: ``--packages NAME=PATH`` repeats, a key/value map no
    signature derives (``cad_server._internal.cli_from_function``)."""
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST

    parser = argparse.ArgumentParser(prog=prog, description="Check one URDF robot description for conformance.")
    parser.add_argument("path", metavar="PATH", type=Path, help="The .urdf file to check.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as blocking.")
    parser.add_argument("--packages", action="append", default=[], metavar="NAME=PATH",
                        help="Resolve package://NAME/... mesh URIs against PATH. Repeatable.")
    parser.add_argument("--verbose", action="store_true", help="Narrate the target on stderr.")
    parser.add_argument("--json", dest=JSON_FLAG_DEST, action="store_true",
                        help="Print the result as one JSON line on stdout instead of human lines.")
    return parser


def _urdf_check(argv: list[str], prog: str) -> int:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST, call_verb

    args = _urdf_parser(prog).parse_args(argv)
    _refuse_other_type("urdf", "check", str(args.path))
    return call_verb(("cad.urdf", "check"),
                     lambda check: check(args.path, strict=bool(args.strict), packages=package_map(args.packages),
                                         verbose=bool(args.verbose)),
                     prog=prog, as_json=bool(getattr(args, JSON_FLAG_DEST)), verbose=bool(args.verbose))


def package_map(entries: Sequence[str]) -> "dict[str, Path] | None":
    """``NAME=PATH`` pairs as the map ``cad.urdf.check`` takes, or None for no roots."""
    if not entries:
        return None
    roots: dict[str, Path] = {}
    for entry in entries:
        name, separator, raw = str(entry).partition("=")
        if not separator or not name.strip() or not raw.strip():
            raise ValueError(f"--packages expects NAME=PATH, got {entry!r}")
        roots[name.strip()] = Path(raw.strip()).expanduser()
    return roots


def _generated_check(document_type: str) -> Callable[[list[str], str], int]:
    """A check whose options are its function's signature (``cad_server._internal.cli_from_function``)."""

    def run(argv: list[str], prog: str) -> int:
        return _checked(document_type, (f"cad.{document_type}", "check"), argv, prog)

    return run


def _engine(verb: str, document_type: str) -> Callable[[list[str], str], int]:
    """An operation that is one of the engine's verbs, run for a source of this type."""

    def run(argv: list[str], prog: str) -> int:
        from cad_server.engine.cli import VERBS, answered, parser_for

        args = parser_for(verb, prog).parse_args(argv)
        source = getattr(args, _ENGINE_SOURCES[verb], None)
        if source is not None:
            _refuse_other_type(document_type, verb, str(source))
        return answered(VERBS[verb][2], args, prog)

    return run


# --- a 3D type's manufacturing check: the trimesh integration's ---------------------------------------


def pull_value(argv: list[str]) -> list[str]:
    """``--pull -z`` as ``--pull=-z``: argparse reads a value that starts with a dash as an option."""
    out: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--pull" and index + 1 < len(argv) and argv[index + 1].startswith("-"):
            out.append(f"--pull={argv[index + 1]}")
            index += 2
            continue
        out.append(token)
        index += 1
    return out


def _manufacturing_check(document_type: str) -> Callable[[list[str], str], int]:
    """``cad <type> check --process molding|printing``: the library's check (``cad.<type>.check``), run here
    when this environment holds the trimesh integration, else in the environment that holds it
    (``cad_server._internal.integration_env``), its options refused here first, before one is made."""

    def run(argv: list[str], prog: str) -> int:
        from cad_server._internal import integration_env

        argv = pull_value(argv)
        target = (f"cad.{document_type}", "check")
        integration = DOCUMENT_TYPES[document_type].operation("check").integration
        if integration_env.carries(integration):
            return _checked(document_type, target, argv, prog)
        return _checked_elsewhere(document_type, target, integration, argv, prog)

    return run


def _checked_elsewhere(document_type: str, target: tuple[str, str], integration: str, argv: list[str],
                       prog: str) -> int:
    from cad._internal.manufacturing import options
    from cad.results import CheckFinding, CheckResult
    from cad_server._internal import integration_env
    from cad_server._internal.cli_from_function import (JSON_FLAG_DEST, _call_arguments, _explicit_option_dests,
                                                        _verb, emit, generated_parser)

    parser = generated_parser(target, prog=prog)
    parsed = parser.parse_args(argv)
    _refuse_other_type(document_type, "check", str(parsed.source))
    positional, keywords = _call_arguments(_verb(target), parsed, explicit_keywords=_explicit_option_dests(parser, argv))

    def said(line: str) -> None:
        print(f"{prog}: {line}", file=sys.stderr, flush=True)

    def measured() -> CheckResult:
        given = {name: value for name, value in keywords.items() if name not in ("process", "candidates")}
        options(document_type, keywords.get("process"), given, candidates=bool(keywords.get("candidates")))
        python = integration_env.environment(integration, said)
        found = integration_env.call(python, document_type, "check", [str(value) for value in positional], keywords)
        return CheckResult(ok=bool(found["ok"]), path=Path(found["path"]),
                           findings=tuple(CheckFinding(**finding) for finding in found.get("findings") or ()),
                           summary=str(found.get("summary") or ""), measurements=found.get("measurements") or {})

    return emit(measured, prog=prog, as_json=bool(getattr(parsed, JSON_FLAG_DEST)), verbose_hint=False)


# --- the KiCad board's own operations: the kicad integration's, and the library's summary ---------------


def _board_parser(prog: str, operation: str) -> argparse.ArgumentParser:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST

    descriptions = {
        "export": "Write a saved KiCad board's fabrication outputs with KiCad's kicad-cli, headless, into a folder.",
        "inspect": "What a saved KiCad board holds: its format, thickness, size, layers, parts and nets.",
    }
    parser = argparse.ArgumentParser(prog=prog, description=descriptions[operation])
    parser.add_argument("board", metavar="BOARD", type=Path, help="the .kicad_pcb (its .kicad_pro beside it)")
    if operation == "export":
        from cad.kicad._export import EXPORTS

        parser.add_argument("--to", required=True, choices=EXPORTS, help="what to write: " + ", ".join(EXPORTS))
        parser.add_argument("-o", "--out", required=True, type=Path, metavar="DIR",
                            help="the folder to write into, made when missing")
    parser.add_argument("--json", dest=JSON_FLAG_DEST, action="store_true",
                        help="print the answer as one JSON line on stdout")
    return parser


def _board_check(argv: list[str], prog: str) -> int:
    return _checked("kicad_pcb", ("cad_server.kicad.check", "check"), argv, prog)


def _checked(document_type: str, target: tuple[str, str], argv: list[str], prog: str) -> int:
    """A generated check run: its file, the function's first parameter as the parser read it (wherever it
    stands among the options: ``--urdf robot.urdf robot.srdf``), refused when it is another type's."""
    import inspect

    from cad_server._internal.cli_from_function import _verb, generated_main, generated_parser

    parsed = generated_parser(target, prog=prog).parse_args(argv)
    first = next(iter(inspect.signature(_verb(target)).parameters))
    source = getattr(parsed, first, None)
    if source is not None:
        _refuse_other_type(document_type, "check", str(source))
    return generated_main(target, argv, prog=prog)


def _answer(as_json: bool, payload: dict, lines: list[str]) -> int:
    import json

    if as_json:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        print("\n".join(lines))
    return 0


def _failed(as_json: bool, prog: str, words: str, status: int = 1) -> int:
    import json

    if as_json:
        print(json.dumps({"ok": False, "error": words}, separators=(",", ":")))
        return 1
    sys.stderr.write(f"{prog}: {words}\n")
    return status


def _board_export(argv: list[str], prog: str) -> int:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST

    args = _board_parser(prog, "export").parse_args(argv)
    _refuse_other_type("kicad_pcb", "export", str(args.board))
    as_json = bool(getattr(args, JSON_FLAG_DEST))
    from cad.kicad._export import export
    from cad.kicad._program import KicadMissingError
    from cad_server.kicad.cli import KicadRunError

    try:
        written = export(args.board, args.to, args.out)
    except (KicadMissingError, KicadRunError) as error:
        return _failed(as_json, prog, str(error))
    return _answer(as_json, {"ok": True, "written": [str(path) for path in written]},
                   [f"wrote {path}" for path in written])


def _board_inspect(argv: list[str], prog: str) -> int:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST

    args = _board_parser(prog, "inspect").parse_args(argv)
    _refuse_other_type("kicad_pcb", "inspect", str(args.board))
    as_json = bool(getattr(args, JSON_FLAG_DEST))
    if not args.board.is_file():
        return _failed(as_json, prog, f"no board {args.board}", 2)
    from cad.kicad_pcb import inspect

    try:
        board = inspect(args.board)
    except (OSError, ValueError) as error:
        return _failed(as_json, prog, f"{type(error).__name__}: {error}")
    size = board.get("size")
    counts = board.get("counts") or {}
    lines = [f"{board['file']}: KiCad {board['format'].get('generator_version') or board['format'].get('version')}"
             + (f", {size[0]:g} x {size[1]:g} mm" if size else "")
             + (f", {board['thickness']:g} mm thick" if board.get("thickness") else ""),
             "counts: " + ", ".join(f"{name} {value}" for name, value in counts.items()),
             "copper: " + ", ".join(board["layers"].get("copper") or [])]
    lines.append("parts:")
    lines += [f"  {part['ref']:<8} {part['value']}  {part['side']}  at {part['at'][0]:g}, {part['at'][1]:g}"
              for part in board.get("parts") or []]
    lines.append("nets:")
    lines += [f"  {net['name']:<12} {net['pads']} pads, {net['tracks']} tracks, {net['vias']} vias, {net['zones']} zones"
              for net in board.get("nets") or []]
    return _answer(as_json, board, lines)


# A type's operations its own code runs, in place of the engine's verb of that name.
_OWN: dict[tuple[str, str], Callable[[list[str], str], int]] = {
    ("kicad_pcb", "check"): _board_check,
    ("kicad_pcb", "export"): _board_export,
    ("kicad_pcb", "inspect"): _board_inspect,
}


#: ``(type, operation) -> run(argv, prog)``: what each type implements, its registry entry's operations.
OPERATIONS: dict[tuple[str, str], Callable[[list[str], str], int]] = {}
for _entry in DOCUMENT_TYPES.values():
    for _name in _entry.operation_names:
        if (_entry.id, _name) in _OWN:
            OPERATIONS[(_entry.id, _name)] = _OWN[(_entry.id, _name)]
        elif _name in _ENGINE_SOURCES:
            OPERATIONS[(_entry.id, _name)] = _engine(_name, _entry.id)
        elif _name == "check" and getattr(_entry.operation(_name), "family", None) == "manufacturing":
            OPERATIONS[(_entry.id, _name)] = _manufacturing_check(_entry.id)
        elif _name == "check":
            OPERATIONS[(_entry.id, _name)] = _urdf_check if _entry.id == "urdf" else _generated_check(_entry.id)
del _entry, _name


def build_parser(document_type: str, operation: str, prog: str | None = None) -> argparse.ArgumentParser:
    """The parser of ``cad <type> <operation>``: its options, exactly as the command parses them."""
    prog = prog or f"cad {document_type} {operation}"
    if (document_type, operation) not in OPERATIONS:
        raise KeyError(f"cad {document_type} has no operation {operation!r}")
    if (document_type, operation) == ("kicad_pcb", "check"):
        from cad_server._internal.cli_from_function import generated_parser

        return generated_parser(("cad_server.kicad.check", "check"), prog=prog)
    if document_type == "kicad_pcb" and operation in ("export", "inspect"):
        return _board_parser(prog, operation)
    if operation in _ENGINE_SOURCES:
        from cad_server.engine.cli import parser_for

        return parser_for(operation, prog)
    if document_type == "urdf":
        return _urdf_parser(prog)
    from cad_server._internal.cli_from_function import generated_parser

    return generated_parser((f"cad.{document_type}", operation), prog=prog)


def operations_of(document_type: str) -> tuple[str, ...]:
    """The operations ``cad <type>`` takes, in the fixed order."""
    return tuple(name for name in DOCUMENT_TYPES[document_type].operation_names if (document_type, name) in OPERATIONS)


def _refuse_other_type(document_type: str, operation: str, source: str) -> None:
    """A file of another type, refused by name before anything runs."""
    suffix = Path(source).suffix
    found = by_extension(suffix) if suffix else None
    if found is not None and found.id != document_type:
        also = f": use cad {found.id} {operation}" if (found.id, operation) in OPERATIONS else \
            f"; cad {found.id} takes {', '.join(operations_of(found.id))}"
        raise _Refused(f"{source} is a {found.id}, not a {document_type}{also}")


class _Refused(Exception):
    """A request refused by name before anything ran: exit status 2."""


def type_usage(document_type: str) -> str:
    """``cad <type> --help``: the type and its operations, from the registry."""
    return (f"usage: cad {document_type} <operation> FILE [options]\n\n{help_text(document_type)}\n\n"
            f"Run 'cad {document_type} <operation> --help' for an operation's options.\n")


def type_main(document_type: str, argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    """``cad <type> <operation> ...``: one operation of one type."""
    argv = list(sys.argv[1:] if argv is None else argv)
    prog = prog or f"cad {document_type}"
    if argv[:1] and argv[0] in {"-h", "--help", "help"}:
        sys.stdout.write(type_usage(document_type))
        return 0
    if not argv:
        sys.stderr.write(f"{prog}: cad {document_type} needs an operation\n\n" + type_usage(document_type))
        return 2
    operation, rest = argv[0], argv[1:]
    run = OPERATIONS.get((document_type, operation))
    if run is None:
        problem = f"cad {document_type} has no operation {operation!r}; it has {', '.join(operations_of(document_type))}"
        sys.stderr.write(f"{prog}: {problem}\n\n" + type_usage(document_type))
        return 2
    try:
        return run(rest, f"{prog} {operation}")
    except _Refused as refused:
        if "--json" in rest:
            import json

            print(json.dumps({"ok": False, "error": str(refused)}))
            return 1
        sys.stderr.write(f"{prog} {operation}: {refused}\n")
        return 2
