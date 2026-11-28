"""``cad <verb> FILE``: the verbs on a file -- ``export``, ``inspect``, ``snapshot``, ``dfm`` and ``fea`` -- each
running what the file's type does for it (``cad.registry.VERBS``, ``operation_for``), the type by the file's suffix.

``cad export SRC DST [--as KIND]`` writes what DST says, like ``cp``: a file, its format by its suffix, or of a KiCad
file a folder or a ``.zip`` too, ``--as`` naming the kind where DST cannot; ``cad inspect FILE [REF]`` says what a
document holds, a robot description's
conformance check (``--strict``, ``--packages``, ``--urdf``), and with ``--interference`` or ``--ranges`` a B-rep's
interference check or its joint stops; ``cad snapshot FILE OUT.png`` draws it; ``cad dfm FILE`` checks that a part
can be made; ``cad fea FILE`` is a B-rep's stress study. A model's document id is an ``xbf``'s source as its
``.xbf`` is, and a share's link this computer's copy of it (``engine.cli.linked``). A file whose type lacks the verb
is refused in one line naming the types that have it, before anything runs (``wrong_type``, exit 2); each type's
options are its own, and its runner (``cad_server.cli.document_types.OPERATIONS``) parses them with the verb's name
as its program's.

``cad <verb> --help`` says every type's options (``build_parser``, the reference's too); ``cad <verb> FILE --help``
the file's type's alone.
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from collections.abc import Callable
from pathlib import Path

__all__ = ["SUMMARIES", "USAGES", "VERBS", "build_parser", "dispatch", "resolve"]

#: The verbs on a file, in the order ``cad --help`` lists them.
VERBS = ("export", "inspect", "snapshot", "dfm", "fea")

#: What each verb does, in a line (``cad --help``, the reference).
SUMMARIES = {
    "export": "write a file to one destination, what DST says: a file by its suffix, or of a KiCad file a folder or a "
              ".zip too (--as KIND where DST cannot say it)",
    "inspect": "what a document holds, or a ref in it; a robot description's conformance check; --interference: which "
               "parts share volume; --ranges: each joint's stops",
    "snapshot": "draw a file as the viewer does, into a PNG",
    "dfm": "check that a part can be made: CNC, sheet metal, injection molding or 3D printing, against general, cited "
           "rules",
    "fea": "a linear static stress study of a part or a bonded assembly: its setup, or with --study and --out the solve",
}

#: Each verb's forms, a line each, as its usage says them.
USAGES = {
    "export": ("cad export SRC DST [--as KIND] [--tolerance MM] [--angle DEG] [--zero STATE] [--json]",),
    "inspect": ("cad inspect FILE [REF] [--query Q] [--json]",
                "cad inspect FILE --interference [--pose POSE]... [--fit A B]... [--min-volume MM3] [--json]",
                "cad inspect FILE --ranges [--step STEP] [--clearance MM] [--joint NAME]... [--verbose] [--json]",
                "cad inspect ROBOT.urdf [--packages NAME=PATH]... [--strict] [--verbose] [--json]",
                "cad inspect ROBOT.srdf [--urdf URDF] [--strict] [--verbose] [--json]",
                "cad inspect BOARD.kicad_pcb [--json] | SCHEMATIC.kicad_sch [REF] [--json]"),
    "snapshot": ("cad snapshot SRC OUT.png [options]", "cad snapshot --job PACKET [SRC] [--out DIR] [options]"),
    "dfm": ("cad dfm FILE [--process cnc|sheet|molding|printing] [the process's options] [--material M] [--strict] "
            "[--json]",),
    "fea": ("cad fea FILE [--occurrence PART] [--json]",
            "cad fea FILE --study STUDY --out DIR [--deck] [--verbose] [--json]"),
}

# The modes of ``cad inspect`` and their flags (``cad.registry.MODES``).
_MODES = {"--interference": "interference", "--ranges": "ranges"}


def _types_said(verb: str, mode: str | None = None) -> str:
    from cad.registry import types_for

    found = list(types_for(verb, mode))
    return f"{', '.join(found[:-1])} and {found[-1]}" if len(found) > 1 else found[0]


def _files_said(verb: str, mode: str | None = None) -> str:
    """The files ``cad <verb>`` takes, by their suffixes: what a refusal names."""
    from cad.registry import DOCUMENT_TYPES, types_for

    found = types_for(verb, mode)
    suffixes = [suffix for name in found for suffix in DOCUMENT_TYPES[name].extensions]
    return f"{', '.join(suffixes[:-1])} or {suffixes[-1]}" if len(suffixes) > 1 else suffixes[0]


def _source_said(verb: str) -> str:
    """What ``cad <verb>`` takes as its source, said in its help with no file named (``build_parser``): every file it
    takes, by its suffix, not the first type's alone (a model's .xbf), and what else its types' sources are."""
    from cad_server.engine.cli import _LINKED

    files = _files_said(verb)
    if verb == "fea":
        return (f"the part or the assembly: a {files} file, a model's .xbf read as the file it is; in Python, the "
                "handle a model's call returns too")
    if verb == "dfm":
        return (f"the file to check, its type by its suffix: {files}, a model's .xbf checked as the file it is; in "
                "Python, the handle a model's call returns too")
    job = "; with --job, drawn in place of every job's input" if verb == "snapshot" else ""
    return (f"the file, its type by its suffix: {files}, a model's .xbf the build the engine holds while the file is "
            f"the one that build wrote, else the file as it is{_LINKED}{job}")


def _export_said(action: argparse.Action) -> argparse.Action:
    """``cad export``'s DST and ``--as`` as its help says them with no file named (``build_parser``): every type's
    destinations and kinds, not a model's alone (the first type's); else the action as it is."""
    from cad._internal.verbs import MODEL_KINDS
    from cad.kicad._export import EXPORTS as BOARD
    from cad.kicad._schematic import EXPORTS as SCHEMATIC

    if action.dest not in ("destinations", "as_"):
        return action
    action = copy.copy(action)
    if action.dest == "as_":
        action.choices = tuple(dict.fromkeys((*MODEL_KINDS, *BOARD, *SCHEMATIC)))
        action.help = ("the kind written, where DST cannot say it: a board's gerbers, drill, odb or pdf into a folder "
                       "or a .zip, its pos or bom into a .csv; given where DST says it, the two must agree")
    else:
        action.help = ("where to write it, a file by its suffix: .step (or .stp), .glb, .stl, .3mf, .dxf, .xbf, .xml "
                       "(MJCF; a board's IPC-2581) or .urdf, a board's .csv (its placement or BOM), a schematic's .pdf, "
                       ".net or .csv; or of a KiCad file a folder (ending in /, or one that is there: made when "
                       "missing) or a .zip, of the files KiCad writes. An output of one file is named as that file, "
                       "never a folder: no name is made up, and a refused export writes nothing")
    return action


# --- what a command line names ------------------------------------------------------------------------------

def _takes_values(verb: str) -> dict[str, int]:
    """Each option of ``cad <verb>`` (every type's) and the words it takes: what finds the source among them."""
    found: dict[str, int] = {}
    for parser in _parsers(verb):
        for action in parser._actions:  # noqa: SLF001 - argparse exposes no public view
            count = 0 if action.nargs == 0 else action.nargs if isinstance(action.nargs, int) else 1
            for flag in action.option_strings:
                found.setdefault(flag, count)
    return found


def _source(verb: str, argv: list[str]) -> str | None:
    """The command line's first positional word, its source: past each option and the words it takes."""
    takes = _takes_values(verb)
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return argv[index + 1] if index + 1 < len(argv) else None
        if token.startswith("-") and token != "-":
            flag, equals, _value = token.partition("=")
            index += 1 + (0 if equals else takes.get(flag, 0))
            continue
        return token
    return None


def _mode(verb: str, argv: list[str]) -> str | None:
    """``cad inspect``'s mode, its flag given (``--interference``, ``--ranges``): refused when both are."""
    if verb != "inspect":
        return None
    named = {_MODES[token] for token in argv[: argv.index("--") if "--" in argv else len(argv)] if token in _MODES}
    if len(named) > 1:
        from cad_server._internal.cli_errors import Failure

        raise Failure("cad inspect takes --interference or --ranges, not both", "usage")
    return next(iter(named), None)


def _type_of(verb: str, source: str) -> str:
    """The document type of ``source`` as ``cad <verb>`` reads it, by its suffix (a model's document id an
    ``xbf``'s): a model's script, and a file of no type, refused by name (``wrong_type``)."""
    from cad.engine.addresses import parts
    from cad.engine.ids import is_id
    from cad.registry import INTEGRATIONS, by_extension
    from cad_server._internal.cli_errors import Failure

    named = parts(source)[0]  # a FILE#REF's file
    if is_id(named):
        return "xbf"
    script = named.partition("::")[0]
    if script.lower().endswith(".py"):
        import shlex

        raise Failure(f"{source} is a model's script, not a document: `cad run {shlex.quote(script)}` builds its models, "
                      f"writes each one's .xbf and prints each one's id, which cad {verb} takes", "wrong_type")
    suffix = Path(named).suffix
    found = by_extension(suffix) if suffix else None
    if found is None:
        # A tool's own file that is no document type (a MuJoCo model's .xml): its integration's command takes it.
        owner = next((entry for entry in INTEGRATIONS.values() if not entry.deprecated
                      and suffix.lower() in entry.files), None)
        tool = (f" (cad {owner.name} {owner.operation_names[0]} takes {' and '.join(owner.files)})"
                if owner is not None else "")
        raise Failure(f"{source} is not a file cad {verb} takes: it takes {_files_said(verb)}{tool}", "wrong_type")
    return found.id


def resolve(verb: str, argv: list[str]) -> tuple[str, str, str | None]:
    """``(document_type, operation, mode)``: what ``cad <verb> ...`` runs, after refusing a source whose type has
    none (``wrong_type``) and a command line with no source (``usage``)."""
    from cad.registry import operation_for
    from cad_server._internal.cli_errors import Failure
    from cad_server.engine.cli import linked

    from cad._internal.verbs import article

    mode = _mode(verb, argv)
    source = _source(verb, argv)
    if source is None:
        raise Failure(f"cad {verb} needs a file: {USAGES[verb][0]}", "usage")
    document_type = _type_of(verb, str(linked(source)))
    operation = operation_for(verb, document_type, mode)
    if operation is None:
        if verb == "dfm" and document_type in ("kicad_pcb", "kicad_sch"):
            check = "drc" if document_type == "kicad_pcb" else "erc"
            raise Failure(f"{source} is {article(document_type)}: cad dfm checks that a part can be made; KiCad's own "
                          f"check of it is cad kicad {check}", "wrong_type")
        flag = f" --{mode}" if mode else ""
        raise Failure(f"{source} is {article(document_type)}, which has no {verb}{flag}: cad {verb}{flag} takes "
                      f"{_types_said(verb, mode)} files", "wrong_type")
    return document_type, operation, mode


# --- each type's runner and parser for a verb -----------------------------------------------------------------

def _runner(verb: str, document_type: str, operation: str) -> Callable[[list[str], str], int]:
    from cad_server.cli.document_types import OPERATIONS

    return OPERATIONS[(document_type, operation)]


def _type_parser(verb: str, document_type: str, operation: str, prog: str) -> argparse.ArgumentParser:
    from cad_server.cli.document_types import build_parser as type_parser

    return type_parser(document_type, operation, prog)


def _parsers(verb: str, prog: str | None = None) -> list[argparse.ArgumentParser]:
    """Every parser a type's runner of ``cad <verb>`` reads its command line by, in the table's order."""
    from cad.registry import DOCUMENT_TYPES, MODES, operation_for

    prog = prog or f"cad {verb}"
    found = []
    for entry in DOCUMENT_TYPES.values():
        for mode in (None, *(MODES if verb == "inspect" else ())):
            operation = operation_for(verb, entry.id, mode)
            if operation is not None and (mode is None or operation == MODES[mode]):
                found.append(_type_parser(verb, entry.id, operation, prog))
    return found


def build_parser(verb: str, argv: list[str] | None = None, *, prog: str | None = None) -> argparse.ArgumentParser:
    """``cad <verb>``'s parser: with a command line that names a file (``argv``), its type's, as the command reads
    it; else every type's options in one (the help and the reference), the first a type takes of each flag."""
    prog = prog or f"cad {verb}"
    if argv is not None:
        try:
            document_type, operation, _mode = resolve(verb, list(argv))
        except Exception:  # noqa: BLE001 - a line no type takes is read by every type's options
            pass
        else:
            return _type_parser(verb, document_type, operation, prog)
    from cad_server._internal.cli_parser import parser as command_parser

    union = command_parser(prog, description=SUMMARIES[verb])
    union.usage = "\n       ".join(USAGES[verb]).replace(f"cad {verb}", "%(prog)s")
    flags: set[str] = {"-h", "--help"}
    for index, parser in enumerate(_parsers(verb, prog)):
        for action in parser._actions:  # noqa: SLF001 - argparse exposes no public view
            if not action.option_strings:
                if index == 0:  # the positionals of the first type that has the verb: its source, and what follows
                    if not union._get_positional_actions():  # noqa: SLF001 - its source, of every file the verb takes
                        action = copy.copy(action)
                        action.help = _source_said(verb)
                    union._add_action(_export_said(action) if verb == "export" else action)  # noqa: SLF001
                continue
            if flags & set(action.option_strings):
                continue
            flags.update(action.option_strings)
            union._add_action(_export_said(action) if verb == "export" else action)  # noqa: SLF001 - shared, or a copy
    return union


# --- the command ------------------------------------------------------------------------------------------------

def _help(verb: str, prog: str) -> int:
    """``cad <verb> --help`` with no file: its forms and every type's options."""
    parser = build_parser(verb, prog=prog)
    sys.stdout.write(parser.format_help())
    sys.stdout.write(f"\nTakes {_files_said(verb)} files"
                     + ("; 'cad export FILE --help' says one type's options" if verb == "export"
                        else f"; 'cad {verb} FILE --help' says one type's options") + ".\n")
    return 0


def dispatch(verb: str, argv: list[str], prog: str | None = None) -> int:
    """``cad <verb> ...``: its source's type's runner, the command line handed to it whole."""
    from cad_server._internal.cli_errors import Failure, wants_json, write
    from cad_server.cli.document_types import pull_value

    prog = prog or f"cad {verb}"
    argv = pull_value(list(argv)) if verb == "dfm" else list(argv)
    if verb == "export":  # a spelling it had (``--to KIND``): answered with the one it has now, nothing run
        from cad_server.cli import _hint

        hint = _hint(["export", *argv])
        if hint is not None:
            return write(Failure(hint, "usage"), prog=prog, as_json=wants_json(argv))
    asked = {"-h", "--help"} & set(argv[: argv.index("--") if "--" in argv else len(argv)])
    if asked and _source(verb, argv) is None:
        return _help(verb, prog)
    if verb == "snapshot" and _source(verb, argv) is None and any(
            token == "--job" or token.startswith("--job=") for token in argv):
        # A job names its own inputs: drawn by the engine's verb, whatever their types.
        from cad_server.engine.cli import VERBS, answered, parser_for

        return answered(VERBS["snapshot"][2], parser_for("snapshot", prog).parse_args(argv), prog)
    try:
        document_type, operation, _mode = resolve(verb, argv)
    except Failure as failure:
        return write(failure, prog=prog, as_json=wants_json(argv))
    return _runner(verb, document_type, operation)(argv, prog)
