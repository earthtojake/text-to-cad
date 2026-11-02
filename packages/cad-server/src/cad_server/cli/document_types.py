"""``cad <document_type> <operation> <file>``: every document type's commands, from the registry.

The shape is one for every type (``cad.registry``): the type's id, then one of the fixed operations
it implements, then its file -- ``cad xbf export arm.xbf arm.step``, ``cad stl snapshot part.stl
part.png``, ``cad srdf check robot.srdf --urdf robot.urdf``. Each operation has one result shape:
``export`` says the files it wrote, ``check`` its findings (each with a severity, a code and a
location; ``--json`` the ``cad.results.CheckResult``). A type's own options live with the type.

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
        from cad_server._internal.cli_from_function import generated_main

        first = next((token for token in argv if not token.startswith("-")), None)
        if first is not None:
            _refuse_other_type(document_type, "check", first)
        return generated_main((f"cad.{document_type}", "check"), argv, prog=prog)

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


#: ``(type, operation) -> run(argv, prog)``: what each type implements, its registry entry's operations.
OPERATIONS: dict[tuple[str, str], Callable[[list[str], str], int]] = {}
for _entry in DOCUMENT_TYPES.values():
    for _name in _entry.operation_names:
        if _name in _ENGINE_SOURCES:
            OPERATIONS[(_entry.id, _name)] = _engine(_name, _entry.id)
        elif _name == "check":
            OPERATIONS[(_entry.id, _name)] = _urdf_check if _entry.id == "urdf" else _generated_check(_entry.id)
del _entry, _name


def build_parser(document_type: str, operation: str, prog: str | None = None) -> argparse.ArgumentParser:
    """The parser of ``cad <type> <operation>``: its options, exactly as the command parses them."""
    prog = prog or f"cad {document_type} {operation}"
    if (document_type, operation) not in OPERATIONS:
        raise KeyError(f"cad {document_type} has no operation {operation!r}")
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
    if not argv or argv[0] in {"-h", "--help", "help"}:
        sys.stdout.write(type_usage(document_type))
        return 0
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
