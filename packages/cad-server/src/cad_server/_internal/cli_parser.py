"""The one parser every ``cad`` command reads its options by: ``parser(...)``, an ``argparse`` parser that
speaks the failure contract (``cli_errors``).

- **No abbreviation.** Only an option's full name and the aliases it declares are read (``allow_abbrev``
  off): adding an option can never change what a prefix of it meant, and ``--p`` is no ``--prune``.
- **One suggestion.** A choice it does not take gets the closest one (``suggest_on_error``), and an option
  it does not take the closest of its own (``unrecognized``), never more than one, and nothing is run on a
  guess.
- **Its usage errors are the contract's.** A command line it cannot read (``error``) is a ``usage``
  failure, exit 2: under ``--json`` -- when the parser takes ``--json`` and the command line gives it -- its
  one JSON document on stdout and nothing else; without it, the usage and the error on stderr, as argparse
  says them.
- **Its checks are the command line's too.** ``checks`` run on what it read, before anything else does --
  a document type's file of another type, an input that is not there -- and a ``Failure`` one raises is said
  as a usage error is, with the exit status of its class.

Every parser of the ``cad`` command's is made here; a policy test holds that none is made otherwise.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from cad_server._internal.cli_errors import Failure, wants_json, write

__all__ = ["Parser", "parser", "suggest", "unrecognized"]


class Parser(argparse.ArgumentParser):
    """``argparse.ArgumentParser`` under the failure contract (see the module); ``checks`` each take the
    parsed namespace and raise ``Failure`` for one they refuse."""

    def __init__(self, *args: Any, checks: Iterable[Callable[[argparse.Namespace], None]] = (),
                 **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("suggest_on_error", True)  # Python 3.14, the floor (packages/cad's requires-python)
        super().__init__(*args, **kwargs)
        self.checks = list(checks)
        self._tokens: list[str] = []

    def parse_known_args(self, args: Sequence[str] | None = None, namespace: Any = None) -> Any:  # type: ignore[override]
        self._tokens = list(sys.argv[1:] if args is None else args)
        return super().parse_known_args(args, namespace)

    def parse_args(self, args: Sequence[str] | None = None, namespace: Any = None) -> Any:  # type: ignore[override]
        parsed, extras = self.parse_known_args(args, namespace)
        if extras:
            self.error(unrecognized(self, extras))
        for check in self.checks:
            try:
                check(parsed)
            except Failure as failure:
                self.fail(failure, as_json=self.answers_json(parsed))
        return parsed

    def json_dest(self) -> str | None:
        """The destination of this parser's ``--json``, or None for a parser that takes none."""
        for action in self._actions:
            if "--json" in action.option_strings:
                return action.dest
        return None

    def answers_json(self, parsed: argparse.Namespace | None = None) -> bool:
        """Whether this command answers in JSON: it takes ``--json``, and its command line gave it (as
        ``parsed`` read it; else as its words name it, for a command line it could not read)."""
        dest = self.json_dest()
        if dest is None:
            return False
        if parsed is not None:
            return bool(getattr(parsed, dest, False))
        return wants_json(self._tokens)

    def error(self, message: str) -> None:  # type: ignore[override]
        self.fail(Failure(message, "usage"), as_json=self.answers_json())

    def fail(self, failure: Failure, *, as_json: bool) -> None:
        """Say ``failure`` -- a usage error as argparse says one, without JSON -- and exit with its status."""
        if as_json:
            write(failure, prog=self.prog, as_json=True)
        elif failure.reason == "usage":
            self.print_usage(sys.stderr)
            sys.stderr.write(f"{self.prog}: error: {failure}\n")
        else:
            write(failure, prog=self.prog, as_json=False)
        self.exit(failure.status)


def parser(prog: str | None = None, **options: Any) -> Parser:
    """The parser of a ``cad`` command (``Parser``): ``argparse.ArgumentParser``'s options, and ``checks``."""
    return Parser(prog=prog, **options)


def suggest(word: str, names: Iterable[str]) -> str | None:
    """The one of ``names`` closest to ``word`` (``difflib``), or None when none is close: a suggestion,
    never run."""
    close = difflib.get_close_matches(word, sorted(set(names)), n=1)
    return close[0] if close else None


def unrecognized(found: argparse.ArgumentParser, extras: Sequence[str]) -> str:
    """argparse's words for arguments a parser does not take, and for the first that looks like an option,
    the one of its own it means: the one it is a prefix of when it is that of one alone (``--p``, which is
    never read as ``--prune``), else the closest (``suggest``)."""
    words = f"unrecognized arguments: {' '.join(extras)}"
    own = [name for name in found._option_string_actions if name.startswith("--")]  # noqa: SLF001
    for token in extras:
        if token.startswith("--") and len(token) > 2:
            stem = token.split("=", 1)[0]
            prefixed = [name for name in own if name.startswith(stem)]
            close = prefixed[0] if len(prefixed) == 1 else suggest(stem, own)
            if close:
                return f"{words} (did you mean {close}?)"
            break
    return words
