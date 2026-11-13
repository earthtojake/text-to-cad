"""``cad <integration> <operation> [FILE]``: an integration's operations on its tool's own files.

A document type is a file cad shows; its commands are ``cad <type> <operation>``
(``cad_server.cli.document_types``). Some files are a tool's own and no document type: cad writes one and
asks the tool about it, and the tool's own app shows it (a MuJoCo model, which MuJoCo Studio opens). What
cad does with such a file is the integration's operation (``cad.registry``: an integration's ``operations``
and the ``files`` they take), one to one with ``cad.<integration>.<operation>``: ``cad mujoco check
robot.xml`` is ``cad.mujoco.check``. A file that has a document type has its operations there, never here.
Where the tool's own files are found by name in its own folders, an operation takes the names and no FILE:
OrcaSlicer's presets (``cad orcaslicer presets machine``, ``cad orcaslicer complete --printer ...``).

An operation's options are its function's signature (``cad_server._internal.cli_from_function``). It runs
in this process where this environment holds the integration (a checkout's; always, for an integration with no
extra, whose code is the library's own), else in the integration's
environment (``cad[<integration>]`` at this installation's release, made on first need:
``cad_server._internal.integration_env``), through the library's runner of one operation.
"""

from __future__ import annotations

import argparse
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
    """A file that is not the tool's own, refused by name before anything runs: a document type's file
    (``wrong_type``, naming its own command), any other file, and one that is not there (``not_found``)."""
    from cad_server._internal.cli_errors import Failure
    from cad_server.cli.document_types import OPERATIONS as TYPE_OPERATIONS
    from cad_server.cli.document_types import operations_of as type_operations

    entry = INTEGRATIONS[integration]
    suffix = Path(source).suffix.lower()
    if suffix not in entry.files:
        found = by_extension(suffix) if suffix else None
        if found is not None:
            checks = [name for name in type_operations(found.id) if name in ("validate", "drc", "erc", "dfm")]
            use = (f": use cad {found.id} {checks[0]}" if checks and (found.id, checks[0]) in TYPE_OPERATIONS
                   else f"; cad {found.id} takes {', '.join(type_operations(found.id))}")
            raise Failure(f"{source} is a {found.id}, not a file cad {integration} {operation} takes "
                          f"({' or '.join(entry.files)}){use}", "wrong_type")
        raise Failure(f"{source} is not a file cad {integration} {operation} takes: it takes "
                      f"{' or '.join(entry.files)}", "wrong_type")
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

        def check(parsed: argparse.Namespace) -> None:
            source = getattr(parsed, "path", None)
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


#: ``(integration, operation) -> run(argv, prog)``: each integration's operations, its registry entry's.
OPERATIONS: dict[tuple[str, str], Callable[[list[str], str], int]] = {
    (entry.name, name): _run(entry.name, name) for entry in INTEGRATIONS.values() for name in entry.operation_names}


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
