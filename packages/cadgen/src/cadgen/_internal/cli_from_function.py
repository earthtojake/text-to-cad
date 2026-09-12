"""Derive a CLI from a public verb function's signature (design/format-doors.md).

A *mirror* command is one whose parser is GENERATED from the function it calls,
so a flag and a parameter cannot drift: adding a keyword-only argument adds a
flag, renaming one renames the flag, and deleting one deletes it. There is no
second place to update and therefore no second place to forget.

The derivation is deliberately a strict SUBSET, so this helper never grows into
an argument-parsing framework:

* Parameters before ``*`` become positionals — optional (``nargs="?"``) when
  they carry a default.
* Keyword-only parameters become ``--kebab-case`` flags; ``bool`` becomes
  ``store_true`` (and must default to ``False``, since a flag can only turn
  something on).
* The allowed annotation set is ``str, int, float, bool, Path`` and ``X | None``
  over those. Anything richer DISQUALIFIES the function from mirror status: it
  must be an ADAPTER instead — a hand-written parser plus an explicit
  signature-sync allowlist (tests/python/packages/cadgen/test_public_surface.py).
* The docstring's summary paragraph becomes the ``--help`` description, and
  ``name: description`` lines in its body become per-argument help. A plain
  convention, so no docstring-parser dependency rides in the runtime.
* The return value is a dataclass: ``--json`` serializes it to one line,
  otherwise it prints human lines. A raised exception becomes
  ``{"ok": false, "error": ...}`` + exit 1.

Stdlib only, and light: building a parser at dispatch costs microseconds, and
nothing here may pull the CAD stack in — ``cadgen <verb> --help`` must stay off
the ~2.5s OCP import. The verb functions keep their own heavy imports inside
their bodies for the same reason.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import inspect
import json
import re
import sys
import types
import typing
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable

# The flag every generated CLI carries. It is part of the SERIALIZATION
# contract rather than the function's signature, so the signature-sync policy
# test exempts it structurally instead of through a per-command allowlist.
JSON_FLAG_DEST = "json_output"

# Annotations a mirror-able verb may use.
_SCALARS: dict[Any, Callable[[str], Any]] = {
    str: str,
    int: int,
    float: float,
    bool: bool,
    Path: Path,
}


class NotDerivable(TypeError):
    """The function is outside the mirror subset; it must be an adapter."""


def _scalar(annotation: Any, *, where: str) -> Any:
    if annotation in _SCALARS:
        return annotation
    raise NotDerivable(
        f"{where}: {annotation!r} is outside the mirror-derivable set "
        f"({', '.join(sorted(t.__name__ for t in _SCALARS))}, or X | None over them)"
    )


def _resolve_annotation(annotation: Any, *, where: str) -> tuple[Any, bool]:
    """``(scalar type, optional?)`` for one annotation, or raise :class:`NotDerivable`."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = typing.get_args(annotation)
        non_none = [arg for arg in args if arg is not type(None)]
        # An OBJECT option: ``str | dict | None`` — CLI-side always one string
        # (a saved name, inline JSON, or a path); the verb interprets it, and
        # library callers pass real dicts through the same parameter.
        if len(args) == 3 and set(non_none) == {str, dict}:
            return str, True
        if len(args) != 2 or len(non_none) != 1:
            raise NotDerivable(
                f"{where}: only ``X | None`` and ``str | dict | None`` unions are "
                f"derivable, got {annotation!r}"
            )
        return _scalar(non_none[0], where=where), True
    return _scalar(annotation, where=where), False


def _repeatable(annotation: Any) -> bool:
    """``tuple[str, ...]`` — a repeatable string flag (``--focus A --focus B``)."""
    return (
        typing.get_origin(annotation) is tuple
        and typing.get_args(annotation) == (str, Ellipsis)
    )


_PARAM_HELP_RE = re.compile(r"^(?P<name>[a-z_][a-z0-9_]*): (?P<text>\S.*)$")


def parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """``(summary, {param: help})`` from the plain convention this module uses.

    The summary is the first paragraph. Per-parameter help is any body line of
    the form ``name: description`` (continuation lines are appended), which is
    both readable as prose in the source and mechanically extractable here.
    """
    if not doc:
        return "", {}
    lines = inspect.cleandoc(doc).splitlines()
    summary_parts: list[str] = []
    index = 0
    while index < len(lines) and lines[index].strip():
        summary_parts.append(lines[index].strip())
        index += 1
    helps: dict[str, str] = {}
    current: str | None = None
    for line in lines[index:]:
        stripped = line.strip()
        match = _PARAM_HELP_RE.match(stripped)
        if match:
            current = match.group("name")
            helps[current] = match.group("text").strip()
            continue
        if not stripped:
            current = None
            continue
        if current is not None:
            helps[current] = f"{helps[current]} {stripped}".strip()
    return " ".join(summary_parts), helps


def _type_hints(func: Callable[..., Any]) -> dict[str, Any]:
    try:
        return typing.get_type_hints(func)
    except Exception as exc:  # noqa: BLE001 - an unresolvable annotation is not derivable
        raise NotDerivable(f"{func.__qualname__}: annotations do not resolve: {exc}") from exc


def function_parameters(func: Callable[..., Any]) -> tuple[str, ...]:
    """The parameter names a generated parser must cover, in signature order."""
    return tuple(inspect.signature(func).parameters)


def parser_dests(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    """Every option/positional destination a parser defines, minus ``--help``."""
    return tuple(
        action.dest
        for action in parser._actions  # noqa: SLF001 - argparse exposes no public view
        if action.dest not in {"help", argparse.SUPPRESS}
    )


def cli_from_function(func: Callable[..., Any], *, prog: str) -> argparse.ArgumentParser:
    """The argparse parser this function's signature implies."""
    summary, param_help = parse_docstring(func.__doc__)
    parser = argparse.ArgumentParser(prog=prog, description=summary)
    hints = _type_hints(func)
    where = func.__qualname__
    for name, parameter in inspect.signature(func).parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            raise NotDerivable(f"{where}: variadic parameter {name!r} is not derivable")
        if name not in hints:
            raise NotDerivable(f"{where}: parameter {name!r} has no annotation")
        help_text = param_help.get(name)
        if parameter.kind is parameter.KEYWORD_ONLY and _repeatable(hints[name]):
            if parameter.default != ():
                raise NotDerivable(
                    f"{where}: repeatable flag {name!r} must default to an empty tuple"
                )
            parser.add_argument(
                "--" + name.replace("_", "-"),
                action="append",
                default=None,
                # The same metavar rule as a scalar flag. De-pluralizing it
                # here read well for a `--tags TAG` and turned `--focus` into
                # `FOCU`, so the repeatable-ness is stated in the help text
                # instead, where it can be said in words.
                metavar=name.rsplit("_", 1)[-1].upper(),
                help=help_text,
            )
            continue
        base, _optional = _resolve_annotation(hints[name], where=f"{where}.{name}")
        if parameter.kind is parameter.KEYWORD_ONLY:
            flag = "--" + name.replace("_", "-")
            if base is bool:
                if parameter.default is not False:
                    raise NotDerivable(
                        f"{where}: bool flag {name!r} must default to False; a flag can "
                        "only turn something on"
                    )
                parser.add_argument(flag, action="store_true", help=help_text)
                continue
            parser.add_argument(
                flag,
                type=base,
                default=None if parameter.default is parameter.empty else parameter.default,
                metavar=name.rsplit("_", 1)[-1].upper(),
                help=help_text,
            )
            continue
        if base is bool:
            raise NotDerivable(f"{where}: positional {name!r} may not be a bool")
        options: dict[str, Any] = {"type": base, "help": help_text, "metavar": name.upper()}
        if parameter.default is not parameter.empty:
            options["nargs"] = "?"
            options["default"] = parameter.default
        parser.add_argument(name, **options)
    parser.add_argument(
        "--json",
        dest=JSON_FLAG_DEST,
        action="store_true",
        help="Print the result as one JSON line on stdout instead of human lines.",
    )
    return parser


def _call_arguments(
    func: Callable[..., Any], namespace: argparse.Namespace
) -> tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for name, parameter in inspect.signature(func).parameters.items():
        value = getattr(namespace, name)
        if parameter.default == () and isinstance(parameter.default, tuple):
            # Repeatable flag: argparse appends into a list (None = never given).
            value = tuple(value or ())
        if parameter.kind is parameter.KEYWORD_ONLY:
            keywords[name] = value
        else:
            positional.append(value)
    return positional, keywords


def _plain(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def result_payload(result: Any) -> dict[str, Any]:
    """One JSON-ready dict for a Result dataclass (``Path`` -> str, tuples -> lists)."""
    if not dataclasses.is_dataclass(result) or isinstance(result, type):
        raise TypeError(f"a verb function must return a Result dataclass, got {type(result)!r}")
    return _plain(dataclasses.asdict(result))


def result_lines(result: Any) -> list[str]:
    """The human rendering: the Result's own ``human_lines()`` when it has one."""
    renderer = getattr(result, "human_lines", None)
    if callable(renderer):
        return [str(line) for line in renderer()]
    return [
        f"{field.name}: {_plain(getattr(result, field.name))}"
        for field in dataclasses.fields(result)
    ]


def emit(
    invoke: Callable[[], Any],
    *,
    prog: str,
    as_json: bool,
    verbose: bool = False,
    verbose_hint: bool = True,
    stdout: Any | None = None,
    stderr: Any | None = None,
) -> int:
    """Call one verb and render its Result — the WHOLE of a command's output.

    Every command in the schema prints through here, generated or not, so a
    hand-written ADAPTER cannot end up serializing differently from a mirror:
    one JSON line under ``--json``, the Result's human lines otherwise, and
    ``{"ok": false, "error": ...}`` + exit 1 for an exception.
    """
    out = stdout if stdout is not None else sys.stdout
    try:
        result = invoke()
    except Exception as exc:  # noqa: BLE001 — the CLI boundary: report, do not traceback
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")), file=out)
            return 1
        from cadgen._internal.cli_errors import report_cli_error

        return report_cli_error(
            exc, tool=prog, verbose=verbose, verbose_hint=verbose_hint, stream=stderr
        )
    if as_json:
        print(json.dumps(result_payload(result), separators=(",", ":")), file=out)
    else:
        for line in result_lines(result):
            print(line, file=out)
    return 0 if getattr(result, "ok", True) else 1


def call_verb(
    target: tuple[str, str],
    invoke: Callable[[Callable[..., Any]], Any],
    *,
    prog: str,
    as_json: bool,
    verbose: bool = False,
    verbose_hint: bool = True,
    stdout: Any | None = None,
) -> int:
    """:func:`emit` for an adapter: it passes its own arguments to the verb."""
    return emit(
        lambda: invoke(_verb(target)),
        prog=prog,
        as_json=as_json,
        verbose=verbose,
        verbose_hint=verbose_hint,
        stdout=stdout,
    )


def run_cli(
    func: Callable[..., Any],
    argv: Sequence[str] | None,
    *,
    prog: str,
    stdout: Any | None = None,
) -> int:
    """Parse ``argv`` against ``func``'s generated parser, call it, print the result."""
    tokens = list(argv) if argv is not None else sys.argv[1:]
    parser = cli_from_function(func, prog=prog)
    args = parser.parse_args(tokens)
    positional, keywords = _call_arguments(func, args)
    return emit(
        lambda: func(*positional, **keywords),
        prog=prog,
        as_json=bool(getattr(args, JSON_FLAG_DEST)),
        verbose=bool(getattr(args, "verbose", False)),
        # The verb's signature decides whether `--verbose` exists at all (only a
        # `verbose` parameter generates it), so the failure hint follows the same
        # source of truth instead of promising a flag this door does not have.
        verbose_hint=hasattr(args, "verbose"),
        stdout=stdout,
    )


# --- the shells the command table dispatches to ------------------------------
# A generated command's module is a two-line shell naming ``(module, verb)``;
# everything else about it is derived here, so there is no per-command parser
# to drift. Importing the verb's module stays LAZY (inside these functions) to
# keep `--help` off the CAD stack.


def _verb(target: tuple[str, str]) -> Callable[..., Any]:
    module_name, attribute = target
    return getattr(importlib.import_module(module_name), attribute)


def generated_parser(target: tuple[str, str], *, prog: str) -> argparse.ArgumentParser:
    return cli_from_function(_verb(target), prog=prog)


def generated_main(
    target: tuple[str, str],
    argv: Sequence[str] | None,
    *,
    prog: str,
) -> int:
    return run_cli(_verb(target), argv, prog=prog)
