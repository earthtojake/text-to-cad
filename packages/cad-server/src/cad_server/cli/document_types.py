"""``cad <document_type> <operation> <file>``: every document type's commands, from the registry.

The shape is one for every type (``cad.registry``): the type's id, then one of the operations it
implements, then its file (or, for ``model``, a model's document id) -- ``cad xbf export arm.xbf
arm.step``, ``cad model export <id> arm.glb``, ``cad stl snapshot part.stl part.png``, ``cad srdf validate
robot.srdf --urdf robot.urdf``. ``export`` and ``snapshot`` are shared by every type that has them; the
others are named for what they do. Each operation has one result shape: ``export`` says the files it
wrote; ``dfm``, ``solve``, ``drc``, ``erc`` and ``validate`` their findings (each with a severity, a code and a
location; ``--json`` the ``cad.results.CheckResult``). A type's own options live with the type.

A 3D type's ``dfm`` (``model``, ``xbf``, ``step``, ``stl``, ``threemf``, ``glb``) is the manufacturing
check, the trimesh integration's: ``cad stl dfm part.stl --process molding --pull -z``, ``cad model dfm
<id> --process printing --candidates``. It runs here when this environment holds trimesh, else in the
environment the engine makes for ``cad[trimesh]`` (``cad_server._internal.integration_env``). A B-rep
type's ``solve`` (``model``, ``xbf``, ``step``) is the stress study: ``cad step solve part.step`` lists the parts,
the pairs that touch and a part's faces a study names, and ``cad step solve part.step --study study.json --out
DIR`` solves it, writing its results into DIR; it runs here when this environment holds the kernel, netgen and
CalculiX, else in the environment of ``cad[build123d,calculix,netgen]``. A KiCad
board's ``drc`` and a schematic's ``erc``, and their ``export``, are the kicad integration's, run the same
way: here when this process runs KiCad itself (``CAD_KICAD_CLI``, or kicode installed here), else in the
environment of ``cad[kicad]``.

``cad <type> --help`` lists the type's operations, worked out from the registry, and ``cad <type>
<operation> --help`` that operation's options. A file of another type is refused by name, before
anything runs: ``part.glb is a glb, not a stl: use cad glb snapshot``; a model's document id given to a
file's type, and a file given to ``model``, the same -- a check of the operation's parser (``_typed``), so
it is the command line's failure (``wrong_type``, exit 2) with ``--json`` and without
(``cad_server._internal.cli_errors``).

Each type's command is its own module (``cad_server.cli.<type>``), so ``python -m
cad_server.cli.step export ...`` runs what ``cad step export ...`` does. Dispatch stays lazy: the
engine and the checks import when an operation runs, never for ``--help``.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from cad.registry import DOCUMENT_TYPES, by_extension, help_text

__all__ = ["OPERATIONS", "build_parser", "operations_of", "type_main", "type_usage"]

# The engine's verbs that are operations (``cad_server.engine.cli.VERBS``), and the attribute of the
# parsed arguments each names its source by.
_ENGINE_SOURCES = {"export": "source", "snapshot": "document", "inspect": "document"}


def _urdf_parser(prog: str) -> argparse.ArgumentParser:
    """``cad urdf validate``'s parser, an ADAPTER's: ``--packages NAME=PATH`` repeats, a key/value map no
    signature derives (``cad_server._internal.cli_from_function``)."""
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="Check one URDF robot description for conformance.")
    parser.add_argument("path", metavar="PATH", type=Path, help="The .urdf file to validate.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as blocking.")
    parser.add_argument("--packages", action="append", default=[], metavar="NAME=PATH",
                        help="Resolve package://NAME/... mesh URIs against PATH. Repeatable.")
    parser.add_argument("--verbose", action="store_true", help="Narrate the target on stderr.")
    parser.add_argument("--json", dest=JSON_FLAG_DEST, action="store_true",
                        help="Print the result as one JSON line on stdout instead of human lines.")
    return parser


def _urdf_validate(argv: list[str], prog: str) -> int:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST, call_verb

    parser = _typed(_urdf_parser(prog), "urdf", "validate", "path")
    parser.checks.append(lambda parsed: _refused_value(package_map, parsed.packages))  # type: ignore[attr-defined]
    args = parser.parse_args(argv)
    return call_verb(("cad.urdf", "validate"),
                     lambda validate: validate(args.path, strict=bool(args.strict), packages=package_map(args.packages),
                                         verbose=bool(args.verbose)),
                     prog=prog, as_json=bool(getattr(args, JSON_FLAG_DEST)), verbose=bool(args.verbose))


def package_map(entries: Sequence[str]) -> "dict[str, Path] | None":
    """``NAME=PATH`` pairs as the map ``cad.urdf.validate`` takes, or None for no roots; ``ArgumentRefused``
    (a ``ValueError``) naming ``--packages`` for one that is no such pair."""
    if not entries:
        return None
    from cad._internal.refused import ArgumentRefused

    roots: dict[str, Path] = {}
    for entry in entries:
        name, separator, raw = str(entry).partition("=")
        if not separator or not name.strip() or not raw.strip():
            raise ArgumentRefused(f"--packages expects NAME=PATH, got {entry!r}")
        roots[name.strip()] = Path(raw.strip()).expanduser()
    return roots


def _refused_value(check: Callable[..., object], *args: object) -> None:
    """``check(*args)``, an argument's own check, with the value it refuses by name (``ArgumentRefused``) the
    command line's failure (``invalid_argument``), said before anything runs."""
    from cad._internal.refused import ArgumentRefused
    from cad_server._internal.cli_errors import Failure

    try:
        check(*args)
    except ArgumentRefused as refused:
        raise Failure(str(refused), "invalid_argument") from None


def _generated(document_type: str, operation: str) -> Callable[[list[str], str], int]:
    """An operation whose options are its function's signature (``cad_server._internal.cli_from_function``)."""

    def run(argv: list[str], prog: str) -> int:
        return _checked(document_type, (f"cad.{document_type}", operation), argv, prog)

    return run


def _engine(verb: str, document_type: str) -> Callable[[list[str], str], int]:
    """An operation that is one of the engine's verbs, run for a source of this type."""

    def run(argv: list[str], prog: str) -> int:
        from cad_server.engine.cli import VERBS, answered, parser_for

        parser = _typed(parser_for(verb, prog, document_type=document_type), document_type, verb, _ENGINE_SOURCES[verb])
        return answered(VERBS[verb][2], parser.parse_args(argv), prog)

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


def _dfm(document_type: str) -> Callable[[list[str], str], int]:
    """``cad <type> dfm --process molding|printing``: the library's manufacturing check (``cad.<type>.dfm``),
    run here when this environment holds the trimesh integration, else in the environment that holds it
    (``cad_server._internal.integration_env``), its options refused here first, before one is made."""

    def run(argv: list[str], prog: str) -> int:
        from cad_server._internal import integration_env

        argv = pull_value(argv)
        target = (f"cad.{document_type}", "dfm")
        integration = "trimesh"
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

    parser = _typed(generated_parser(target, prog=prog), document_type, target[1], "source")
    parsed = parser.parse_args(argv)
    positional, keywords = _call_arguments(_verb(target), parsed, explicit_keywords=_explicit_option_dests(parser, argv))

    def said(line: str) -> None:
        print(f"{prog}: {line}", file=sys.stderr, flush=True)

    def measured() -> CheckResult:
        given = {name: value for name, value in keywords.items() if name not in ("process", "candidates")}
        options(document_type, keywords.get("process"), given, candidates=bool(keywords.get("candidates")))
        python = integration_env.environment(integration, said)
        found = integration_env.call(python, document_type, target[1], [str(value) for value in positional], keywords)
        return CheckResult(ok=bool(found["ok"]), path=Path(found["path"]),
                           findings=tuple(CheckFinding(**finding) for finding in found.get("findings") or ()),
                           summary=str(found.get("summary") or ""), measurements=found.get("measurements") or {})

    return emit(measured, prog=prog, as_json=bool(getattr(parsed, JSON_FLAG_DEST)), verbose_hint=False)


# --- a B-rep type's stress study: read by the kernel, meshed by netgen, solved by CalculiX ------------------


def _solve(document_type: str) -> Callable[[list[str], str], int]:
    """``cad <type> solve SOURCE [--study STUDY --out DIR]``: the library's stress study
    (``cad.<type>.solve``), run here when this environment holds the kernel, netgen and CalculiX, else in the
    environment of ``cad[build123d,calculix,netgen]`` (``cad_server._internal.integration_env``), its options refused
    here first, before one is made."""

    def run(argv: list[str], prog: str) -> int:
        from cad._internal.fea.operation import INTEGRATION
        from cad_server._internal import integration_env
        from cad_server._internal.cli_from_function import _verb, generated_parser, run_cli

        target = (f"cad.{document_type}", "solve")
        if integration_env.carries(INTEGRATION):
            parser = _typed(generated_parser(target, prog=prog), document_type, "solve", "source")
            return run_cli(_verb(target), argv, prog=prog, parser=parser)
        return _solve_elsewhere(document_type, target, INTEGRATION, argv, prog)

    return run


def _solve_elsewhere(document_type: str, target: tuple[str, str], integration: str, argv: list[str], prog: str) -> int:
    from cad._internal.fea.operation import options
    from cad.results import FeaResult
    from cad_server._internal import integration_env
    from cad_server._internal.cli_from_function import (JSON_FLAG_DEST, _call_arguments, _explicit_option_dests,
                                                        _verb, emit, generated_parser)

    parser = _typed(generated_parser(target, prog=prog), document_type, target[1], "source")
    parsed = parser.parse_args(argv)
    positional, keywords = _call_arguments(_verb(target), parsed, explicit_keywords=_explicit_option_dests(parser, argv))

    def said(line: str) -> None:
        print(f"{prog}: {line}", file=sys.stderr, flush=True)

    def studied() -> FeaResult:
        options(study=keywords.get("study"), out=keywords.get("out"), occurrence=keywords.get("occurrence"),
                deck=bool(keywords.get("deck")))
        python = integration_env.environment(integration, said)
        # Paths as absolute text: the runner's process reads them as the command would, in this folder; a model's
        # document id as it is.
        plain = {name: str(Path(value).expanduser().resolve()) if isinstance(value, Path) else value
                 for name, value in keywords.items()}
        sources = [str(value) if document_type == "model" else str(Path(value).expanduser().resolve())
                   for value in positional]
        found = integration_env.call(python, document_type, target[1], sources, plain)
        return FeaResult.from_data(found)

    return emit(studied, prog=prog, as_json=bool(getattr(parsed, JSON_FLAG_DEST)),
                verbose=bool(getattr(parsed, "verbose", False)), verbose_hint=True)


# --- the KiCad board's own operations: the kicad integration's, and the library's summary ---------------


def _board_parser(prog: str, operation: str) -> argparse.ArgumentParser:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST
    from cad_server._internal.cli_parser import parser as command_parser

    descriptions = {
        "export": "Write a saved KiCad board's fabrication, assembly or 3D output with KiCad's kicad-cli, headless, "
                  "into a folder.",
        "inspect": "What a saved KiCad board holds: its format, thickness, size, layers, parts and nets.",
    }
    parser = command_parser(prog, description=descriptions[operation])
    parser.add_argument("board", metavar="BOARD", type=Path, help="the .kicad_pcb (its .kicad_pro beside it)")
    if operation == "export":
        from cad.kicad._export import EXPORTS

        parser.add_argument("--to", required=True, choices=EXPORTS,
                            help="what to write: gerbers and drill (a folder of files), pos (placement CSV), bom (the "
                                 "schematic's parts CSV), step and glb (3D), odb (ODB++ zip), ipc2581, pdf (a front and "
                                 "a back fabrication drawing) or dxf (the outline and holes)")
        parser.add_argument("-o", "--out", required=True, type=Path, metavar="DIR",
                            help="the folder to write into, made when missing")
    parser.add_argument("--json", dest=JSON_FLAG_DEST, action="store_true",
                        help="print the answer as one JSON line on stdout")
    return parser


def _runs_kicad_here() -> bool:
    """Whether this process runs KiCad itself (``CAD_KICAD_CLI`` names one, or kicode is installed here);
    else a board's DRC, a schematic's ERC and their exports run in the environment of ``cad[kicad]``."""
    from cad.kicad._program import carried

    return carried()


def _kicad_elsewhere(document_type: str, operation: str, args: list, kwargs: dict, prog: str) -> dict:
    """``cad.<document_type>.<operation>`` run in the environment of ``cad[kicad]``, made first when it is not."""
    from cad_server._internal import integration_env

    def said(line: str) -> None:
        print(f"{prog}: {line}", file=sys.stderr, flush=True)

    return integration_env.call(integration_env.environment("kicad", said), document_type, operation, args, kwargs)


def _kicad_rules(document_type: str, operation: str) -> Callable[[list[str], str], int]:
    """A KiCad file's rules check (a board's ``drc``, a schematic's ``erc``), the kicad integration's: run here
    when this process runs KiCad, else in the environment of ``cad[kicad]``, its file refused here first."""

    def run(argv: list[str], prog: str) -> int:
        target = (f"cad.{document_type}", operation)
        if _runs_kicad_here():
            return _checked(document_type, target, argv, prog)
        from cad.results import CheckFinding, CheckResult
        from cad_server._internal.cli_from_function import JSON_FLAG_DEST, emit, generated_parser

        parsed = _typed(generated_parser(target, prog=prog), document_type, operation,
                        _first_parameter(target)).parse_args(argv)
        source = vars(parsed)[_first_parameter(target)]

        def checked() -> CheckResult:
            found = _kicad_elsewhere(document_type, operation, [str(Path(source).expanduser().resolve())], {}, prog)
            return CheckResult(ok=bool(found["ok"]), path=Path(found["path"]),
                               findings=tuple(CheckFinding(**finding) for finding in found.get("findings") or ()),
                               summary=str(found.get("summary") or ""), measurements=found.get("measurements") or {})

        return emit(checked, prog=prog, as_json=bool(getattr(parsed, JSON_FLAG_DEST)), verbose_hint=False)

    return run


def _first_parameter(target: tuple[str, str]) -> str:
    import inspect

    from cad_server._internal.cli_from_function import _verb

    return next(iter(inspect.signature(_verb(target)).parameters))


def _checked(document_type: str, target: tuple[str, str], argv: list[str], prog: str) -> int:
    """A generated operation's run: its file, the function's first parameter as the parser read it (wherever
    it stands among the options: ``--urdf robot.urdf robot.srdf``), refused when it is another type's, and each
    file its options name refused when it is not there (``_present``)."""
    from cad_server._internal.cli_from_function import _verb, generated_parser, run_cli

    parser = _present(_typed(generated_parser(target, prog=prog), document_type, target[1], _first_parameter(target)))
    return run_cli(_verb(target), argv, prog=prog, parser=parser)


def _present(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """A generated operation's ``parser`` (``cli_from_function``) with the check that each file one of its
    options names is there -- a ``Path`` option of a check is a file it reads (``cad srdf validate --urdf
    robot.urdf``) --, a file that is not there being the command line's failure (``not_found``), as the
    operation's own file is (``_typed``), said before anything runs. Only a generated parser's: a hand-written
    one's ``Path`` may be a folder to write (``cad kicad_pcb export -o DIR``)."""
    from cad_server._internal.cli_errors import Failure

    named = [action for action in parser._actions if action.option_strings and action.type is Path]  # noqa: SLF001

    def check(parsed: argparse.Namespace) -> None:
        for action in named:
            given = getattr(parsed, action.dest, None)
            if given is not None and not os.path.exists(os.path.expanduser(str(given))):
                raise Failure(f"{max(action.option_strings, key=len)} {given}: no such file", "not_found")

    if named:
        parser.checks.append(check)  # type: ignore[attr-defined]
    return parser


def _answer(as_json: bool, payload: dict, lines: list[str]) -> int:
    import json

    if as_json:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        print("\n".join(lines))
    return 0


def _failed(as_json: bool, prog: str, words: str, reason: str = "failed") -> int:
    """A failure said by the contract (``cli_errors.write``): its words, the status its ``reason`` sets."""
    from cad_server._internal.cli_errors import Failure, write

    return write(Failure(words, reason), prog=prog, as_json=as_json)


def _kicad_export(document_type: str) -> Callable[[list[str], str], int]:
    """A KiCad file's export (``--to KIND -o DIR``), the kicad integration's: run here when this process runs
    KiCad, else in the environment of ``cad[kicad]``."""

    def run(argv: list[str], prog: str) -> int:
        from cad_server._internal.cli_from_function import JSON_FLAG_DEST

        parser = _board_parser if document_type == "kicad_pcb" else _schematic_parser
        named = "board" if document_type == "kicad_pcb" else "schematic"
        args = _typed(parser(prog, "export"), document_type, "export", named).parse_args(argv)
        given = getattr(args, named)
        as_json = bool(getattr(args, JSON_FLAG_DEST))
        source, out = Path(given).expanduser().resolve(), Path(args.out).expanduser().resolve()
        try:
            if _runs_kicad_here():
                import importlib

                done = importlib.import_module(f"cad.{document_type}").export(source, args.to, out)
                written, warnings = [str(path) for path in done.written], list(done.warnings)
            else:
                from cad_server._internal.integration_env import Failed

                try:
                    found = _kicad_elsewhere(document_type, "export", [str(source), args.to, str(out)], {}, prog)
                except Failed as error:
                    raise RuntimeError(str(error)) from None
                written = [str(path) for path in found.get("written") or ()]
                warnings = list(found.get("warnings") or ())
        except (RuntimeError, OSError, ValueError) as error:
            return _failed(as_json, prog, str(error))
        for line in warnings:
            print(f"{prog}: warning: {line}", file=sys.stderr)
        return _answer(as_json, {"ok": True, "to": args.to, "written": written, "warnings": warnings},
                       [f"wrote {path}" for path in written])

    return run


def _board_inspect(argv: list[str], prog: str) -> int:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST

    args = _typed(_board_parser(prog, "inspect"), "kicad_pcb", "inspect", "board").parse_args(argv)
    as_json = bool(getattr(args, JSON_FLAG_DEST))
    if not args.board.is_file():
        return _failed(as_json, prog, f"no board {args.board}", "not_found")
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


# --- the KiCad schematic's own operations: the kicad integration's, the library's summary and still -----


def _schematic_parser(prog: str, operation: str) -> argparse.ArgumentParser:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST
    from cad_server._internal.cli_parser import parser as command_parser

    if operation == "snapshot":
        from cad_server.engine.cli import parser_for

        parser = parser_for("snapshot", prog)
        parser.add_argument("--sheet", metavar="PATH",
                            help="the sheet to draw, by its path: / (the root, the default), /Power/; the same as "
                                 "--display '{\"sheet\": PATH}'")
        parser.add_argument("--border", action="store_true", help="draw the page's edge (off by default)")
        return parser
    descriptions = {
        "export": "Write a saved KiCad schematic's outputs with KiCad's kicad-cli, headless, into a folder: a pdf of "
                  "every sheet, an svg per sheet, the netlist (the board imports it) or a BOM.",
        "inspect": "What a saved KiCad schematic holds: its sheets, parts and nets, read from its project's root; "
                   "with REF, what that reference names (#U3, #U3.7, #net:VBUS, #sheet:/Power/, #wire:<uuid>).",
    }
    parser = command_parser(prog, description=descriptions[operation])
    parser.add_argument("schematic", metavar="SCHEMATIC", type=Path,
                        help="the .kicad_sch (any sheet of its project: the whole hierarchy is read)")
    if operation == "export":
        from cad.kicad._schematic import EXPORTS

        parser.add_argument("--to", required=True, choices=EXPORTS, help="what to write: " + ", ".join(EXPORTS))
        parser.add_argument("-o", "--out", required=True, type=Path, metavar="DIR",
                            help="the folder to write into, made when missing")
    else:
        parser.add_argument("ref", metavar="REF", nargs="?", help="a reference to resolve: #U3, #U3.7, #net:GND")
    parser.add_argument("--json", dest=JSON_FLAG_DEST, action="store_true",
                        help="print the answer as one JSON line on stdout")
    return parser


def _schematic_inspect(argv: list[str], prog: str) -> int:
    from cad_server._internal.cli_from_function import JSON_FLAG_DEST

    args = _typed(_schematic_parser(prog, "inspect"), "kicad_sch", "inspect", "schematic").parse_args(argv)
    as_json = bool(getattr(args, JSON_FLAG_DEST))
    if not args.schematic.is_file():
        return _failed(as_json, prog, f"no schematic {args.schematic}", "not_found")
    from cad.kicad_sch import inspect

    try:
        found = inspect(args.schematic, args.ref)
    except (OSError, ValueError) as error:
        return _failed(as_json, prog, f"{type(error).__name__}: {error}")
    counts = found["counts"]
    lines = [f"{found['file']}: KiCad {found['format'].get('generator') or found['format'].get('version')}"
             + (f", in {found['root']}'s hierarchy" if found["root"] != found["file"] else ""),
             "counts: " + ", ".join(f"{name} {value}" for name, value in counts.items()), "sheets:"]
    lines += [f"  {sheet['path']:<16} page {sheet['page']:<4} {sheet['file']}  {sheet['symbols']} symbols"
              for sheet in found["sheets"]]
    lines.append("parts:")
    lines += [f"  {part['ref']:<8} {part['value']}  {part['footprint'] or '(no footprint)'}  on {part['sheet']}"
              for part in found["parts"]]
    lines.append("nets:")
    lines += [f"  {net['name']:<20} {', '.join(net['pins'])}" for net in found["nets"]]
    lines += [f"warning: {warning}" for warning in found["warnings"]]
    if "resolved" in found:
        import json

        lines.append(f"{args.ref}: {json.dumps(found['resolved'])}")
    return _answer(as_json, found, lines)


def _schematic_snapshot(argv: list[str], prog: str) -> int:
    """``cad kicad_sch snapshot``: the engine's verb, ``--sheet`` and ``--border`` folded into its display."""
    import json

    from cad_server.engine.cli import VERBS, answered

    args = _typed(_schematic_parser(prog, "snapshot"), "kicad_sch", "snapshot", "document").parse_args(argv)
    sheet, border = args.sheet, args.border
    del args.sheet, args.border
    if sheet is not None or border:
        given = args.display
        # Refused as the snapshot refuses its own (``cad.engine.snapshot``): a file that is not there, and JSON
        # that does not read, are the command line's, said before anything renders.
        if given and given.strip().endswith(".json") and not Path(given.strip()).expanduser().is_file():
            return _failed(bool(args.json), prog, f"--display {given.strip()}: no such file", "not_found")
        try:
            if given and given.strip().endswith(".json"):
                given = Path(given.strip()).expanduser().read_text(encoding="utf-8")
            display = json.loads(given) if given else {}
        except (OSError, ValueError) as error:  # a JSON error, or a file that cannot be read as text
            return _failed(bool(args.json), prog, f"--display is not JSON: {error}", "invalid_argument")
        if not isinstance(display, dict):
            return _failed(bool(args.json), prog, "--display is a schematic's display object: {sheet, border}",
                           "invalid_argument")
        display.update({**({"sheet": sheet} if sheet is not None else {}), **({"border": True} if border else {})})
        args.display = json.dumps(display)
    return answered(VERBS["snapshot"][2], args, prog)


# A type's operations its own code runs, in place of the engine's verb of that name.
_OWN: dict[tuple[str, str], Callable[[list[str], str], int]] = {
    ("kicad_pcb", "drc"): _kicad_rules("kicad_pcb", "drc"),
    ("kicad_pcb", "export"): _kicad_export("kicad_pcb"),
    ("kicad_pcb", "inspect"): _board_inspect,
    ("kicad_sch", "erc"): _kicad_rules("kicad_sch", "erc"),
    ("kicad_sch", "export"): _kicad_export("kicad_sch"),
    ("kicad_sch", "inspect"): _schematic_inspect,
    ("kicad_sch", "snapshot"): _schematic_snapshot,
}


#: ``(type, operation) -> run(argv, prog)``: what each type implements, its registry entry's operations.
OPERATIONS: dict[tuple[str, str], Callable[[list[str], str], int]] = {}
for _entry in DOCUMENT_TYPES.values():
    for _name in _entry.operation_names:
        if (_entry.id, _name) in _OWN:
            OPERATIONS[(_entry.id, _name)] = _OWN[(_entry.id, _name)]
        elif _name in _ENGINE_SOURCES:
            OPERATIONS[(_entry.id, _name)] = _engine(_name, _entry.id)
        elif _name == "dfm" and getattr(_entry.operation(_name), "integration", None) == "trimesh":
            OPERATIONS[(_entry.id, _name)] = _dfm(_entry.id)
        elif _name == "solve" and getattr(_entry.operation(_name), "integration", None) == "calculix":
            OPERATIONS[(_entry.id, _name)] = _solve(_entry.id)
        elif (_entry.id, _name) == ("urdf", "validate"):
            OPERATIONS[(_entry.id, _name)] = _urdf_validate
        else:
            OPERATIONS[(_entry.id, _name)] = _generated(_entry.id, _name)
del _entry, _name


def build_parser(document_type: str, operation: str, prog: str | None = None) -> argparse.ArgumentParser:
    """The parser of ``cad <type> <operation>``: its options, exactly as the command parses them."""
    prog = prog or f"cad {document_type} {operation}"
    if (document_type, operation) not in OPERATIONS:
        raise KeyError(f"cad {document_type} has no operation {operation!r}")
    if (document_type, operation) in (("kicad_pcb", "drc"), ("kicad_sch", "erc")):
        from cad_server._internal.cli_from_function import generated_parser

        return generated_parser((f"cad.{document_type}", operation), prog=prog)
    if document_type == "kicad_pcb" and operation in ("export", "inspect"):
        return _board_parser(prog, operation)
    if document_type == "kicad_sch":
        return _schematic_parser(prog, operation)
    if operation in _ENGINE_SOURCES:
        from cad_server.engine.cli import parser_for

        return parser_for(operation, prog, document_type=document_type)
    if document_type == "urdf":
        return _urdf_parser(prog)
    from cad_server._internal.cli_from_function import generated_parser

    return generated_parser((f"cad.{document_type}", operation), prog=prog)


def operations_of(document_type: str) -> tuple[str, ...]:
    """The operations ``cad <type>`` takes, in the fixed order."""
    return tuple(name for name in DOCUMENT_TYPES[document_type].operation_names if (document_type, name) in OPERATIONS)


def _typed(parser: argparse.ArgumentParser, document_type: str, operation: str, attribute: str) -> argparse.ArgumentParser:
    """``parser`` (the command's, ``cad_server._internal.cli_parser``) with the check that the source it reads
    as ``attribute`` is the type's and is there (``_refuse_other_type``): a source of another type, and a file
    that is not there, are the command line's failures, said the same for every type before anything runs."""

    def check(parsed: argparse.Namespace) -> None:
        source = getattr(parsed, attribute, None)
        if source is not None:
            _refuse_other_type(document_type, operation, str(source))

    parser.checks.append(check)  # type: ignore[attr-defined]
    return parser


def _refuse_other_type(document_type: str, operation: str, source: str) -> None:
    """A source of another type, refused by name before anything runs (``Failure``, ``wrong_type``): a file
    of another type or of no type, a model's document id given to a file's type, a file given to ``model``;
    and a file of the type's that is not there (``not_found``), whichever the type."""
    from cad.engine.addresses import parts
    from cad.engine.ids import is_id
    from cad_server._internal.cli_errors import Failure

    def use(other: str) -> str:
        return f": use cad {other} {operation}" if (other, operation) in OPERATIONS else \
            f"; cad {other} takes {', '.join(operations_of(other))}"

    given = parts(source)[0]  # a FILE#REF's file, a path that holds a '#' itself (project#1/part.step) whole
    entry = DOCUMENT_TYPES[document_type]
    if is_id(given):
        if entry.has_file:
            raise Failure(f"{source} is a model's document id, not a {entry.suffix} file{use('model')}", "wrong_type")
        return
    script = given.partition("::")[0]
    if script.lower().endswith(".py"):
        # A model's script where its document is wanted: what builds the document, and what takes it.
        import shlex

        then = (f", which cad model {operation} takes" if ("model", operation) in OPERATIONS else "")
        raise Failure(f"{source} is a model's script, not {'a document id' if not entry.has_file else f'a {document_type} file'}"
                      f": `cad run {shlex.quote(script)}` builds its models and prints each one's id{then}", "wrong_type")
    suffix = Path(given).suffix
    found = by_extension(suffix) if suffix else None
    if found is not None and found.id != document_type:
        raise Failure(f"{source} is a {found.id}, not a {document_type}{use(found.id)}", "wrong_type")
    if not entry.has_file:
        raise Failure(f"cad model takes a model's document id (cad run SCRIPT.py prints it), not {source!r}",
                      "wrong_type")
    if found is None:
        raise Failure(f"{source} is not a {document_type} file: cad {document_type} takes "
                      f"{' or '.join(entry.extensions)}", "wrong_type")
    if not os.path.exists(os.path.expanduser(given)):
        raise Failure(f"no such file: {source}", "not_found")


def type_usage(document_type: str) -> str:
    """``cad <type> --help``: the type and its operations, from the registry."""
    what = "FILE" if DOCUMENT_TYPES[document_type].has_file else "ID"
    return (f"usage: cad {document_type} <operation> {what} [options]\n\n{help_text(document_type)}\n\n"
            f"Run 'cad {document_type} <operation> --help' for an operation's options.\n")


def type_main(document_type: str, argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    """``cad <type> <operation> ...``: one operation of one type."""
    argv = list(sys.argv[1:] if argv is None else argv)
    prog = prog or f"cad {document_type}"
    if argv[:1] and argv[0] in {"-h", "--help", "help"}:
        sys.stdout.write(type_usage(document_type))
        return 0
    if not argv:
        return _no_operation(prog, document_type, f"cad {document_type} needs an operation", argv, usage=True)
    operation, rest = argv[0], argv[1:]
    run = OPERATIONS.get((document_type, operation))
    if run is None:
        from cad_server._internal.cli_parser import suggest

        close = suggest(operation, operations_of(document_type))
        return _no_operation(prog, document_type, f"cad {document_type} has no operation {operation!r}"
                             + (f" (did you mean {close!r}?)" if close else "")
                             + f"; it has {', '.join(operations_of(document_type))}; 'cad {document_type} --help' "
                               "says what each does", rest)
    return run(rest, f"{prog} {operation}")


def _no_operation(prog: str, document_type: str, problem: str, argv: list[str], *, usage: bool = False) -> int:
    """A type's command line that names none of its operations: the command line's failure (``usage``), said
    as an unknown command is (``cad_server.cli._unknown``) -- under ``--json`` its JSON document alone, else
    its line on stderr, the type's help after it only for a command line that names no operation at all
    (``usage``), never after one it does not have."""
    from cad_server._internal.cli_errors import Failure, wants_json, write

    if wants_json(argv) or not usage:
        return write(Failure(problem, "usage"), prog=prog, as_json=wants_json(argv))
    sys.stderr.write(f"{prog}: {problem}\n\n" + type_usage(document_type))
    return 2
