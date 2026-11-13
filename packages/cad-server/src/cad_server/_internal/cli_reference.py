"""The ``cad`` command's reference, read off its parsers: every command, each document type's and each
integration's operations, with its usage line, its description, its arguments and its options.

``python -m cad_server._internal.cli_reference --docs`` prints it as the JSON the documentation site reads; a test
holds the site's copy to it, so the reference cannot drift from the command. Nothing here describes a
command by hand: each entry is its parser's own words (``cad_server.cli.build_parser_for``), the one-line
summary the dispatcher lists it by, and, for ``run``, which has no parser of its own (uv judges its
options), its usage and help as ``cad run --help`` says them. An option hidden from ``--help``
(``argparse.SUPPRESS``) is hidden here too, as is ``-h, --help``, which every command takes.

The output is deterministic: commands in the order ``cad --help`` lists them, no paths or addresses, and a
usage line formatted here rather than by argparse, whose wrapping depends on the terminal's width.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

__all__ = ["as_docs", "as_docs_json", "command_reference", "main"]

# The option every command takes, said once by the page rather than once per command.
_HELP_FLAGS = frozenset({"-h", "--help"})


def _metavar(action: argparse.Action, default: str) -> str:
    """An action's value as argparse's usage names it: its metavar, else ``{a,b}`` for choices, else
    ``default`` (a positional's dest, an option's dest upper-cased)."""
    if action.metavar is not None:
        return action.metavar if isinstance(action.metavar, str) else " ".join(action.metavar)
    if action.choices is not None:
        return "{" + ",".join(str(choice) for choice in action.choices) + "}"
    return default


def _value(action: argparse.Action, default: str) -> str:
    """The words an action takes on the command line (argparse's ``_format_args``, without its formatter)."""
    name = _metavar(action, default)
    nargs = action.nargs
    if nargs is None:
        return name
    if nargs == argparse.OPTIONAL:
        return f"[{name}]"
    if nargs == argparse.ZERO_OR_MORE:
        return f"[{name} ...]"
    if nargs == argparse.ONE_OR_MORE:
        return f"{name} [{name} ...]"
    if nargs == argparse.REMAINDER:
        return "..."
    if nargs == argparse.PARSER:
        return f"{name} ..."
    if isinstance(nargs, int):
        return " ".join([name] * nargs)
    return name


def _takes_value(action: argparse.Action) -> bool:
    return action.nargs != 0


def _hidden(action: argparse.Action) -> bool:
    return action.help == argparse.SUPPRESS or bool(_HELP_FLAGS & set(action.option_strings))


def _usage_word(action: argparse.Action) -> str:
    """One action as the usage line says it, without the brackets an optional option wears."""
    if not action.option_strings:
        return _value(action, action.dest)
    flag = max(action.option_strings, key=lambda text: (text.startswith("--"), len(text)))  # its long name
    return f"{flag} {_value(action, action.dest.upper())}" if _takes_value(action) else flag


def _usage(parser: argparse.ArgumentParser, prog: str) -> str:
    """The command's usage on one line: its own ``usage`` where it declares one, else options first and
    positionals after, as argparse orders them, a mutually exclusive group said as one ``[a | b]``."""
    if parser.usage:
        return " ".join((parser.usage % {"prog": prog}).split())
    groups = {id(action): group for group in parser._mutually_exclusive_groups  # noqa: SLF001 - no public view
              for action in group._group_actions}  # noqa: SLF001
    words: list[str] = []
    said: set[int] = set()
    actions = [action for action in parser._actions if not _hidden(action)]  # noqa: SLF001
    for action in [*(a for a in actions if a.option_strings), *(a for a in actions if not a.option_strings)]:
        group = groups.get(id(action))
        if group is not None:
            if id(group) in said:
                continue
            said.add(id(group))
            members = [_usage_word(member) for member in group._group_actions if not _hidden(member)]  # noqa: SLF001
            words.append(("(" if group.required else "[") + " | ".join(members) + (")" if group.required else "]"))
        elif action.option_strings and not action.required:
            words.append(f"[{_usage_word(action)}]")
        else:
            words.append(_usage_word(action))
    return " ".join([prog, *words])


def _help(action: argparse.Action, prog: str) -> str | None:
    """An action's help with argparse's ``%(default)s``-style fields filled, as ``--help`` prints it."""
    if not action.help:
        return None
    fields = {**vars(action), "prog": prog}
    if isinstance(fields.get("choices"), (list, tuple, set, frozenset, dict)):
        fields["choices"] = ", ".join(str(choice) for choice in action.choices)  # type: ignore[union-attr]
    try:
        return " ".join((action.help % fields).split())
    except (KeyError, TypeError, ValueError):
        return " ".join(action.help.split())


def _jsonable(value: Any) -> Any:
    """A default as JSON says it, or None for one with no plain value (a callable, an object)."""
    if value is None or value is argparse.SUPPRESS or isinstance(value, (bool, int, float, str)):
        return None if value is argparse.SUPPRESS else value
    if isinstance(value, (list, tuple)) and all(isinstance(item, (bool, int, float, str)) for item in value):
        return list(value)
    return None


def _repeatable(action: argparse.Action) -> bool:
    return isinstance(action, (argparse._AppendAction, argparse._AppendConstAction,  # noqa: SLF001
                               argparse._ExtendAction, argparse._CountAction))  # noqa: SLF001


def _choices(action: argparse.Action) -> list[str] | None:
    return None if action.choices is None else [str(choice) for choice in action.choices]


def command_reference(parser: argparse.ArgumentParser, command: str, summary: str | None = None) -> dict[str, Any]:
    """One command's entry, read off its parser: ``command`` (``cad xbf export``), the ``summary`` it is listed
    by, its ``usage`` line, ``description`` and ``epilog``, its positional ``arguments`` and its ``options``."""
    arguments: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for action in parser._actions:  # noqa: SLF001 - argparse exposes no public view
        if _hidden(action):
            continue
        if not action.option_strings:
            arguments.append({
                "name": _value(action, action.dest) if action.nargs == argparse.PARSER else _metavar(action, action.dest),
                "help": _help(action, command), "choices": _choices(action),
                "optional": action.nargs in (argparse.OPTIONAL, argparse.ZERO_OR_MORE),
                "repeatable": action.nargs in (argparse.ZERO_OR_MORE, argparse.ONE_OR_MORE)
                              or (isinstance(action.nargs, int) and action.nargs > 1),
            })
            continue
        takes = _takes_value(action)
        default = _jsonable(action.default) if takes else None
        options.append({
            "flags": list(action.option_strings),
            "metavar": _value(action, action.dest.upper()) if takes else None,
            "help": _help(action, command), "choices": _choices(action),
            "default": None if default in ("", []) else default,
            "required": bool(action.required), "repeatable": _repeatable(action),
        })
    return {
        "command": command, "summary": summary, "usage": _usage(parser, command),
        "description": " ".join(parser.description.split()) if parser.description else None,
        "epilog": " ".join(parser.epilog.split()) if parser.epilog else None,
        "arguments": arguments, "options": options,
    }


def _no_parser(name: str, summary: str) -> dict[str, Any]:
    """A command with no parser of its own (``run``): its usage and help as its ``--help`` says them."""
    import importlib

    from cad_server import cli

    module = importlib.import_module(cli._COMMANDS[name][0])  # noqa: SLF001 - the dispatcher's own table
    usage = " ".join(str(module.USAGE).removeprefix("usage:").split())
    return {"command": f"cad {name}", "summary": summary, "usage": usage,
            "description": " ".join(module.description().split()), "epilog": None, "arguments": [], "options": []}


def as_docs() -> dict[str, Any]:
    """The whole command: its ``usage``, each document type's operations (``documentTypes``), each
    integration's (``integrations``), and the other ``commands``, as ``cad --help`` lists them; their
    descriptions and help in ``texts``, each once (``_shared``)."""
    from cad.registry import DOCUMENT_TYPES, INTEGRATIONS
    from cad_server import cli
    from cad_server.cli import document_types, integrations

    def operation(owner: Any, name: str, parser: argparse.ArgumentParser, group: str) -> dict[str, Any]:
        found = owner.operation(name)
        return command_reference(parser, f"cad {group} {name}", found.summary if found is not None else None)

    types = [{
        "name": entry.id, "summary": entry.title,
        "usage": f"cad {entry.id} <operation> {'FILE' if entry.has_file else 'ID'} [options]",
        "operations": [operation(entry, name, document_types.build_parser(entry.id, name), entry.id)
                       for name in document_types.operations_of(entry.id)],
    } for entry in DOCUMENT_TYPES.values()]
    tools = [{
        "name": name, "summary": INTEGRATIONS[name].summary,
        "usage": f"cad {name} <operation> FILE [options]",
        "operations": [operation(INTEGRATIONS[name], op, integrations.build_parser(name, op), name)
                       for op in integrations.operations_of(name)],
    } for name in cli.INTEGRATION_COMMANDS]
    commands = []
    for name in sorted(cli._COMMANDS):  # noqa: SLF001 - the dispatcher's own table, in its --help order
        summary = cli._COMMANDS[name][1]  # noqa: SLF001
        parser = cli.build_parser_for(name)
        commands.append(_no_parser(name, summary) if parser is None
                        else command_reference(parser, f"cad {name}", summary))
    head = cli._USAGE_HEAD.removeprefix("usage:")  # noqa: SLF001
    return _shared({"usage": " ".join(head.split()), "documentTypes": types, "integrations": tools,
                    "commands": commands})


# The fields whose words many commands share (every type's snapshot takes the same options): each is said
# once, in ``texts``, and named by its index there.
_TEXT_FIELDS = ("description", "help")


def _shared(reference: dict[str, Any]) -> dict[str, Any]:
    """``reference`` written once: each ``description`` and ``help`` an index into ``texts`` (in the order
    first met), a description that only repeats its command's summary left out, and every field that says
    nothing (null, false, an empty list) left out."""
    texts: dict[str, int] = {}

    def walk(value: Any) -> Any:
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, dict):
            return value
        if value.get("description") is not None and value.get("description") == value.get("summary"):
            value = {**value, "description": None}
        return {key: (texts.setdefault(item, len(texts)) if key in _TEXT_FIELDS else walk(item))
                for key, item in value.items() if item is not None and item is not False and item != []}

    shared = walk(reference)
    return {**shared, "texts": list(texts)}


def as_docs_json() -> str:
    """``as_docs`` as the file the documentation site reads."""
    return json.dumps(as_docs(), indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--docs"]:
        sys.stdout.write(as_docs_json())
        return 0
    sys.stderr.write("usage: python -m cad_server._internal.cli_reference --docs\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
