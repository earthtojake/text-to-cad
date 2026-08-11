"""Compact failure reporting for the CAD CLIs.

A generator that raises used to reach the interpreter uncaught, so an ordinary authoring
mistake printed a 62-line, 4.2 KB traceback whose one useful line -- the exception -- was
last, under ~50 frames of ``runpy``, the launcher, and cadgen internals. A `gen_step()`
missing its return printed 43 lines to say ``must return one value``.

What a caller actually needs is the failure and WHERE IN THEIR MODEL it happened. Those
frames are already identifiable: :func:`is_first_party_source_file` is the same predicate
the source-closure capture uses to tell model code from the stdlib, site-packages, and the
running runtime. So the report keeps the model's own frames and drops everything else.

``--verbose`` still prints the full traceback -- when the fault IS in cadgen, the internal
frames are the point.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import TextIO

# Deep recursion in a generator (a parametric model calling itself) can produce hundreds of
# identical model frames. The innermost few are where the failure is.
_MAX_FRAMES = 6


def _display(filename: str) -> str:
    """Cwd-relative where that is meaningful, otherwise the tail.

    A runtime frame's absolute path runs through the symlinked skill bundle and is longer
    than the line it is annotating; the last few components identify the module just as
    well without burying the message above it.
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


def _model_frames(exc: BaseException) -> list[traceback.FrameSummary]:
    """The frames in the caller's own CAD sources, outermost first.

    Everything else -- the launcher, cadgen, build123d/OCP, the stdlib -- is runtime: it is
    the same in every failure and says nothing about which model broke.
    """
    from cadgen._internal.source_hash import is_first_party_source_file

    frames: list[traceback.FrameSummary] = []
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            path = Path(frame.filename).resolve()
        except (OSError, ValueError):
            continue
        if is_first_party_source_file(path):
            frames.append(frame)
    return frames


def report_cli_error(
    exc: BaseException,
    *,
    tool: str,
    verbose: bool = False,
    stream: TextIO | None = None,
) -> int:
    """Print ``exc`` as a CLI failure and return the exit code (always 1).

    Under ``verbose`` this is the raw traceback, unchanged -- a cadgen bug needs its own
    frames. Otherwise it is the exception plus the model frames that led to it.
    """
    out = stream if stream is not None else sys.stderr
    if verbose:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=out)
        return 1

    def line(text: str) -> None:
        print(f"[{tool}] {text}", file=out)

    detail = str(exc).strip()
    line(f"FAILED: {type(exc).__name__}: {detail}" if detail else f"FAILED: {type(exc).__name__}")

    frames = _model_frames(exc)
    if frames:
        if len(frames) > _MAX_FRAMES:
            line(f"  ... {len(frames) - _MAX_FRAMES} earlier frame(s) omitted")
        for frame in frames[-_MAX_FRAMES:]:
            line(f"  {_display(frame.filename)}:{frame.lineno} in {frame.name}")
            if frame.line:
                line(f"      {frame.line.strip()}")
    else:
        # Nothing of the caller's ran -- a validation or resolution error raised before the
        # generator was reached. Name the frame that raised so it is still diagnosable; the
        # message itself usually already names the offending file.
        raised = traceback.extract_tb(exc.__traceback__)
        if raised:
            innermost = raised[-1]
            line(f"  raised in {_display(innermost.filename)}:{innermost.lineno}")

    line("re-run with --verbose for the full traceback")
    return 1
