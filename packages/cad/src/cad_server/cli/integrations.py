"""``cad <integration> <operation> [<file>]``: an integration's operations on its tool's own files.

A file cad shows has a document type, and the verbs take it (``cad export``, ``cad inspect``, ...:
``cad_server.cli.verbs``). What a tool does to its own files is the integration's operation (``cad.registry``: an
integration's ``operations`` and the ``files`` they take), one to one with ``cad.<integration>.<operation>``: a
file of no document type, which cad writes and asks the tool about and the tool's own app shows (``cad mujoco check
robot.xml`` is ``cad.mujoco.check``), and a tool's own checks of a document type's file, by the tool's name
(KiCad's: ``cad kicad drc board.kicad_pcb``, ``cad kicad erc sheet.kicad_sch``, ``cad.kicad.drc``,
``cad.kicad.erc``). A deprecated integration has no command: its command line answers with what to do instead
(``cad_server.cli``'s hints).

An operation's options are its function's signature (``cad_server._internal.cli_from_function``). It runs
in this process where this environment holds the integration (a checkout's; always, for an integration with no
extra, whose code is the library's own), else in the integration's
environment (``cad[<integration>]`` at this installation's release, made on first need:
``cad_server._internal.integration_env``), through the library's runner of one operation; KiCad's checks where
this process runs KiCad itself (``CAD_KICAD_CLI``, or kicode here), as the KiCad files' exports do
(``cad_server.cli.document_types``).
"""

from __future__ import annotations

import argparse
import inspect as _inspect
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from cad.registry import INTEGRATIONS, by_extension, integration_help

__all__ = ["OPERATIONS", "build_parser", "integration_main", "integration_usage", "operations_of"]


def operations_of(integration: str) -> tuple[str, ...]:
    """The operations ``cad <integration>`` takes."""
    return INTEGRATIONS[integration].operation_names


def build_parser(integration: str, operation: str, prog: str | None = None) -> argparse.ArgumentParser:
    """The parser of ``cad <integration> <operation>``: its options, exactly as the command parses them."""
    from cad_server._internal.cli_from_function import generated_parser

    if operation not in operations_of(integration):
        raise KeyError(f"cad {integration} has no operation {operation!r}")
    return generated_parser((f"cad.{integration}", operation), prog=prog or f"cad {integration} {operation}")


def _refuse_other_file(integration: str, operation: str, source: str) -> None:
    """A file the operation does not take, refused by name before anything runs: a file the integration's other
    operation takes (``wrong_type``, naming that one), a document type's file (naming the verb that checks it), any
    other file, and one that is not there (``not_found``)."""
    from cad_server._internal.cli_errors import Failure

    entry = INTEGRATIONS[integration]
    takes = entry.files_of(operation)
    suffix = Path(source).suffix.lower()
    if suffix not in takes:
        other = next((name for name in entry.operation_names if suffix in entry.files_of(name)), None)
        if other is not None:
            raise Failure(f"{source} is not a file cad {integration} {operation} takes ({' or '.join(takes)}): "
                          f"cad {integration} {other} checks it", "wrong_type")
        found = by_extension(suffix) if suffix else None
        if found is not None:
            from cad.registry import operation_for

            check = "inspect" if operation_for("inspect", found.id) == "validate" else \
                "dfm" if operation_for("dfm", found.id) else "inspect" if operation_for("inspect", found.id) else None
            raise Failure(f"{source} is a {found.id}, not a file cad {integration} {operation} takes "
                          f"({' or '.join(takes)})" + (f": cad {check} takes it" if check else ""), "wrong_type")
        raise Failure(f"{source} is not a file cad {integration} {operation} takes: it takes "
                      f"{' or '.join(takes)}", "wrong_type")
    if not os.path.exists(os.path.expanduser(source)):
        raise Failure(f"no such file: {source}", "not_found")


def _run(integration: str, operation: str) -> Callable[[list[str], str], int]:
    def run(argv: list[str], prog: str) -> int:
        from cad.results import CheckFinding, CheckResult
        from cad_server._internal import integration_env
        from cad_server._internal.cli_from_function import (JSON_FLAG_DEST, _call_arguments, _explicit_option_dests,
                                                            _verb, emit)

        verb = _verb((f"cad.{integration}", operation))
        parser = build_parser(integration, operation, prog)
        named = next(iter(_inspect.signature(verb).parameters))

        def check(parsed: argparse.Namespace) -> None:
            source = getattr(parsed, named, None)
            if source is not None:
                _refuse_other_file(integration, operation, str(source))

        parser.checks.append(check)  # type: ignore[attr-defined]
        parsed = parser.parse_args(argv)
        positional, keywords = _call_arguments(verb, parsed, explicit_keywords=_explicit_option_dests(parser, argv))

        def said(line: str) -> None:
            print(f"{prog}: {line}", file=sys.stderr, flush=True)

        def elsewhere() -> CheckResult:
            python = integration_env.environment(integration, said)
            found = integration_env.call(python, integration, operation,
                                         [str(Path(value).expanduser().resolve()) for value in positional], keywords)
            return CheckResult(ok=bool(found["ok"]), path=Path(found["path"]),
                               findings=tuple(CheckFinding(**finding) for finding in found.get("findings") or ()),
                               summary=str(found.get("summary") or ""), measurements=found.get("measurements") or {})

        def here() -> object:
            return verb(*positional, **keywords)

        return emit(here if integration_env.carries(integration) else elsewhere, prog=prog,
                    as_json=bool(getattr(parsed, JSON_FLAG_DEST)), verbose=bool(getattr(parsed, "verbose", False)))

    return run


def _kicad(operation: str) -> Callable[[list[str], str], int]:
    """KiCad's own check (``cad kicad drc``, ``cad kicad erc``), as the KiCad files' exports run: where this process
    runs KiCad, else in the environment of ``cad[kicad]`` (``document_types.kicad_rules``)."""
    from cad_server.cli.document_types import kicad_rules

    return kicad_rules(operation, lambda source: _refuse_other_file("kicad", operation, source))


#: ``(integration, operation) -> run(argv, prog)``: each integration's operations, its registry entry's; a deprecated
#: integration's none (its command line is answered with what to do instead: ``cad_server.cli``).
OPERATIONS: dict[tuple[str, str], Callable[[list[str], str], int]] = {
    (entry.name, name): _kicad(name) if entry.name == "kicad" else _run(entry.name, name)
    for entry in INTEGRATIONS.values() if not entry.deprecated for name in entry.operation_names}


def integration_usage(integration: str) -> str:
    """``cad <integration> --help``: the integration and its operations, from the registry."""
    file = " FILE" if INTEGRATIONS[integration].files else ""
    return (f"usage: cad {integration} <operation>{file} [options]\n\n{integration_help(integration)}\n\n"
            f"Run 'cad {integration} <operation> --help' for an operation's options.\n")


def integration_main(integration: str, argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    """``cad <integration> <operation> ...``: one operation of one integration."""
    from cad_server._internal.cli_errors import Failure, wants_json, write

    argv = list(sys.argv[1:] if argv is None else argv)
    prog = prog or f"cad {integration}"
    if argv[:1] and argv[0] in {"-h", "--help", "help"}:
        sys.stdout.write(integration_usage(integration))
        return 0
    if not argv:
        problem = f"cad {integration} needs an operation"
        if wants_json(argv):
            return write(Failure(problem, "usage"), prog=prog, as_json=True)
        sys.stderr.write(f"{prog}: {problem}\n\n" + integration_usage(integration))
        return 2
    operation, rest = argv[0], argv[1:]
    run = OPERATIONS.get((integration, operation))
    if run is None:
        from cad_server._internal.cli_parser import suggest

        close = suggest(operation, operations_of(integration))
        return write(Failure(f"cad {integration} has no operation {operation!r}"
                             + (f" (did you mean {close!r}?)" if close else "")
                             + f"; it has {', '.join(operations_of(integration))}; 'cad {integration} --help' says what "
                               "each does", "usage"), prog=prog, as_json=wants_json(rest))
    return run(rest, f"{prog} {operation}")
