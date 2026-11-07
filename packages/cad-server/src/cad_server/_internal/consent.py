"""Consent for a command that destroys: ``cad uninstall`` (and ``--purge``), ``cad delete``, ``cad doctor
--prune`` and ``cad server --rotate-token`` (``cad setup`` asks nothing: installing is what was asked).

Each says its plan first -- what it removes, with counts -- and then:

- **where a person can be asked** (``interactive``: no ``--json``, stdin and stderr terminals, not CI), the
  question on stderr, ``... (y/N)``, and their answer read from stdin: ``y`` or ``yes`` goes on, anything
  else -- an empty line, end of input -- changes nothing (``declined``, exit 1);
- **where nobody can be** (an agent, a pipe, ``--json``, CI), nothing, unless the command line says yes
  (``-y``, ``--yes``): ``confirmation_required``, exit 2, naming the exact command with ``--yes`` (under
  ``--json``, ``"userActionRequired": true`` and ``"next"``), so whoever runs it asks the person first.

``--yes`` answers this question and no other: it supplies no input and picks no target. A dry run never
asks. The standard library alone.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Sequence

from cad_server._internal.cli_errors import Failure

__all__ = ["add_yes", "confirm", "interactive", "retry"]

_OFF = ("", "0", "false", "no", "off")


def add_yes(parser: argparse.ArgumentParser, what: str) -> None:
    """``-y``/``--yes`` on a destructive command's parser: ``what`` it answers yes to."""
    parser.add_argument("-y", "--yes", action="store_true",
                        help=f"{what} without asking; where nobody can be asked (an agent, a pipe, --json) the "
                             "command does nothing without it")


def interactive(as_json: bool = False) -> bool:
    """Whether a person can be asked here: no answer in JSON, stdin and stderr terminals, not CI."""
    if as_json or str(os.environ.get("CI") or "").strip().lower() not in _OFF:
        return False
    try:
        return bool(sys.stdin and sys.stdin.isatty() and sys.stderr and sys.stderr.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def retry(prog: str, argv: Sequence[str]) -> str:
    """The command line that was run, with ``--yes``: what a person runs to go on."""
    words = [*prog.split(), *[word for word in argv if word not in ("-y", "--yes")], "--yes"]
    return shlex.join(words)


def confirm(action: str, question: str, *, yes: bool, as_json: bool, command: str,
            preview: Sequence[str] = ()) -> None:
    """Go on, or raise the ``Failure`` that says why not (see the module). ``action`` is what is about to be
    done, in words (``deleting 2 documents``); where a person can be asked, ``preview``'s lines and then
    ``question (y/N)`` go to stderr and their answer is read; ``command`` is the command line with
    ``--yes``, named where nobody can be asked."""
    if yes:
        return
    if not interactive(as_json):
        raise Failure(f"{action} needs a yes, and no one can be asked here (no terminal, or --json): nothing was "
                      f"changed; `{command}` says yes", "confirmation_required", next=[command], user_action=True)
    for line in preview:
        print(line, file=sys.stderr)
    print(f"{question} (y/N) ", end="", file=sys.stderr, flush=True)
    answer = sys.stdin.readline()
    if answer.strip().lower() not in ("y", "yes"):
        raise Failure("nothing was changed", "declined")
