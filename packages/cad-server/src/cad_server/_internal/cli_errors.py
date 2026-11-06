"""The ``cad`` command's one failure contract, and the compact report of a generated CLI's failure.

**The contract.** A failure's class sets its exit status, the same with ``--json`` and without
(``REASONS``): 2 for the command line and its input -- a command or an option the command does not take,
an argument missing or out of range, a file of another document type, an input that is not there, a
destructive command run where no one can be asked and no ``--yes`` given (``consent``) -- which fails the
same way until the call changes; 1 for a failure of the work itself (a build, a render, a tool, the engine
out of reach, a mistake of ours, a destructive command the person said no to); 130 for an interrupt.
Under ``--json`` every failure is ONE JSON document on stdout,
the result's channel, so a caller reading it always finds an answer, and nothing else is written there:
``{"ok": false, "error": <its words>, "reason": <a stable snake_case code>}``, with
``"userActionRequired": true`` and ``"next"`` (the commands that would go on) where a person must act;
no traceback, but with ``--verbose``, on stderr. Without ``--json`` the failure's words go to stderr.

``Failure`` is the exception a command raises to say one, ``classify`` the class of any other exception,
and ``write`` the one writer; the parser every command reads its options by (``cli_parser``) says its
usage errors through it, and ``wants_json`` is the one reading of a command line that no parser read (an
unknown command, a crash past every command's own report).

**The compact report.** A generated command's verb that raises would otherwise reach the interpreter as
a long traceback whose one useful line -- the exception -- comes last, under the launcher's and cadgen's
frames. What a caller needs is the failure and where it was raised, so that is what is printed without
``--json`` (``report_cli_error``). ``--verbose`` still prints the full traceback: when the fault IS in
cadgen, the internal frames are the point.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

#: Every reason a failure is said by, and the exit status its class sets. Stable: an agent branches on
#: them, so one is added, never renamed.
REASONS: dict[str, int] = {
    # The command line and its input: the same call fails again until it changes.
    "usage": 2,                  # a command or option it does not take, an argument missing, a value its parser refuses
    "invalid_argument": 2,       # a value read and refused by name before anything ran: out of range, a pose a document lacks
    "wrong_type": 2,             # a file of another document type, a model's id given to a file's type, a file given to model
    "not_found": 2,              # an input that is not there: a file, a document the engine has no record of or does not hold
    "confirmation_required": 2,  # a destructive command where no one can be asked, without --yes: nothing was changed
    # The work.
    "declined": 1,               # the person answered no to a destructive command's question: nothing was changed
    "engine_unavailable": 1,     # the engine server could not be reached or started
    "failed": 1,                 # the work failed: a build, a render, an export, a tool it ran
    "internal_error": 1,         # a mistake in text-to-cad's own code
    # An interrupt (Ctrl-C).
    "canceled": 130,
}
USAGE = REASONS["usage"]
FAILED = REASONS["failed"]


class Failure(Exception):
    """A command's failure, said once where the command ends (``write``): its words, its ``reason`` (one
    of ``REASONS``, which sets the exit status), and for one a person must act on, what they would run
    (``next``) and that they must (``user_action``)."""

    def __init__(self, words: str, reason: str = "failed", *, next: Sequence[str] = (),  # noqa: A002 - the key's name
                 user_action: bool = False) -> None:
        if reason not in REASONS:
            raise ValueError(f"no failure reason {reason!r}; the reasons are {', '.join(REASONS)}")
        super().__init__(words)
        self.reason = reason
        self.next = tuple(next)
        self.user_action = user_action

    @property
    def status(self) -> int:
        return REASONS[self.reason]


def _is(error: BaseException, module: str, name: str) -> bool:
    """Whether ``error`` is an instance of ``module.name``, told without importing ``module``."""
    return any(kind.__module__ == module and kind.__name__ == name for kind in type(error).__mro__)


def classify(error: BaseException) -> Failure:
    """The failure an exception is, by its class: a ``Failure`` as it is; an interrupt ``canceled``; the
    engine out of reach (``ConnectionError``) ``engine_unavailable``; a document the engine does not hold
    (``cad.engine.serve.NotHeld``) ``not_found``; an argument the library refused by name
    (``cad._internal.refused.ArgumentRefused``) ``invalid_argument``; anything else ``failed``."""
    if isinstance(error, Failure):
        return error
    if isinstance(error, KeyboardInterrupt):
        return Failure("canceled", "canceled")
    if isinstance(error, ConnectionError):
        return Failure(failure_text(error), "engine_unavailable")
    if _is(error, "cad.engine.serve", "NotHeld"):
        return Failure(failure_text(error), "not_found")
    if _is(error, "cad._internal.refused", "ArgumentRefused"):
        return Failure(failure_text(error), "invalid_argument")
    return Failure(failure_text(error), "failed")


def document(failure: Failure) -> dict[str, Any]:
    """The JSON a failure is said in under ``--json``."""
    found: dict[str, Any] = {"ok": False, "error": str(failure), "reason": failure.reason}
    if failure.user_action:
        found["userActionRequired"] = True
    if failure.next:
        found["next"] = list(failure.next)
    return found


def write(failure: Failure, *, prog: str, as_json: bool, stdout: TextIO | None = None,
          stderr: TextIO | None = None) -> int:
    """Say ``failure`` once -- under ``as_json`` its document (``document``) as one line on stdout, else
    ``<prog>: <its words>`` on stderr -- and return the exit status its class sets."""
    if as_json:
        print(json.dumps(document(failure), separators=(",", ":")), file=stdout or sys.stdout, flush=True)
    else:
        print(f"{prog}: {failure}", file=stderr or sys.stderr, flush=True)
    return failure.status


def options(argv: Sequence[str]) -> list[str]:
    """A command line's words before ``--``, which ends its options."""
    words = list(argv)
    return words[:words.index("--")] if "--" in words else words


def wants_json(argv: Sequence[str]) -> bool:
    """Whether a command line asks for its answer as JSON (``--json`` among its options): read where no
    parser read it -- a command that is none, a crash past every command's own report."""
    return "--json" in options(argv)


def wants_verbose(argv: Sequence[str]) -> bool:
    """Whether a command line asks for a failure's whole traceback (``--verbose``)."""
    return "--verbose" in options(argv)


def _display(filename: str) -> str:
    """Cwd-relative where that is meaningful, otherwise the tail.

    A runtime frame's absolute path is longer than the line it is annotating; the last
    few components identify the module just as well without burying the message above it.
    """
    try:
        resolved = Path(filename).resolve()
    except (OSError, ValueError):
        return filename
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        parts = resolved.parts
        return ("…/" + "/".join(parts[-3:])) if len(parts) > 3 else resolved.as_posix()


def failure_text(exc: BaseException) -> str:
    """The one line a failure is reported as where only its text fits (a ``--json``
    envelope's ``error``): the exception's message, or, for one raised with none (a bare
    ``AssertionError``), its type and where it was raised -- an empty string names
    nothing."""
    detail = str(exc).strip()
    if detail:
        return detail
    raised = traceback.extract_tb(exc.__traceback__)
    if not raised:
        return type(exc).__name__
    innermost = raised[-1]
    return f"{type(exc).__name__} (raised in {_display(innermost.filename)}:{innermost.lineno})"


def report_cli_error(
    exc: BaseException,
    *,
    tool: str,
    verbose: bool = False,
    verbose_hint: bool = True,
    stream: TextIO | None = None,
) -> int:
    """Print ``exc`` as a CLI failure and return the exit code (always 1).

    Under ``verbose`` this is the raw traceback, unchanged -- a cadgen bug needs its own
    frames. Otherwise it is the exception and the frame that raised it.

    ``verbose_hint`` is whether the caller ACCEPTS ``--verbose``: a command whose
    parser has no such flag must not be told to re-run with it. Only the caller
    knows, so it says so; the default is the flag-bearing case.
    """
    out = stream if stream is not None else sys.stderr
    if verbose:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=out)
        return 1

    def line(text: str) -> None:
        print(f"[{tool}] {text}", file=out)

    detail = str(exc).strip()
    line(f"FAILED: {type(exc).__name__}: {detail}" if detail else f"FAILED: {type(exc).__name__}")
    raised = traceback.extract_tb(exc.__traceback__)
    if raised:
        innermost = raised[-1]
        line(f"  raised in {_display(innermost.filename)}:{innermost.lineno}")

    # A kernel the OS refused to load is no mistake of the caller's and no frame explains it:
    # on Windows 11 that is Smart App Control, and the reader needs to be told so.
    from cad_server._internal.kernel_load_hint import kernel_load_hint

    for hint in kernel_load_hint(exc) or ():
        line(hint)

    if verbose_hint:
        line("re-run with --verbose for the full traceback")
    return 1


def report(exc: BaseException, *, prog: str, as_json: bool, verbose: bool = False, verbose_hint: bool = True,
           stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """A command's failure said by the contract, and its exit status: under ``as_json`` its document
    (the traceback on stderr too, with ``verbose``); without it, one of a known class (a ``Failure``, a
    refusal, the engine out of reach) in its words, and any other exception as the compact report
    (``report_cli_error``)."""
    failure = classify(exc)
    if as_json:
        if verbose:
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=stderr or sys.stderr)
        return write(failure, prog=prog, as_json=True, stdout=stdout)
    if isinstance(exc, Failure) or failure.reason != "failed":
        return write(failure, prog=prog, as_json=False, stderr=stderr)
    return report_cli_error(exc, tool=prog, verbose=verbose, verbose_hint=verbose_hint, stream=stderr)
