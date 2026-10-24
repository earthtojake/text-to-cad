"""Compact failure reporting for the CLIs generated from a verb's signature.

A verb that raises would otherwise reach the interpreter uncaught, and an ordinary mistake
would print a long traceback whose one useful line -- the exception -- comes last, under the
launcher's and cadgen's frames. What a caller needs is the failure and where it was raised,
so that is what is printed. ``--verbose`` still prints the full traceback: when the fault IS
in cadgen, the internal frames are the point.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import TextIO


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
    from cadgen._internal.kernel_load_hint import kernel_load_hint

    for hint in kernel_load_hint(exc) or ():
        line(hint)

    if verbose_hint:
        line("re-run with --verbose for the full traceback")
    return 1
