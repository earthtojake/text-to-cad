"""Painting a build's phases onto a terminal.

Separate from the code that RUNS builds on purpose. This is imported by the snapshot CLI,
which is pinned by tests/python/skills/cad/snapshot/test_cli.py to import no heavy CAD
modules at all -- and while these few hundred lines lived in ``_internal/generation``,
reaching for a progress line dragged OCP and build123d in behind it.

Nothing here knows what a build is. It renders :class:`ProgressEvent`s, which is why the
same painter serves a STEP package, a drawing, an export and a snapshot render.
"""

from __future__ import annotations

import contextlib
import sys
from typing import Callable, Iterator, TextIO

from cadgen.cli_logging import CliLogger
from cadgen.coordination import ProgressEvent, render_progress_bar


class InlineProgressLine:
    """The transient bottom line of a model's build, plus the finished lines above it.

    ``update`` repaints in place with ``\\r``; ``commit`` freezes the current line with a
    newline and starts a fresh one below it. That pairing is what makes the build read as a
    sequence: each phase is live while it runs and then settles into a durable line with its
    duration, instead of one line mutating through four phases and erasing the evidence.

    Disabled (and completely silent) when the stream is not a tty: a redirected log wants the
    logger's lines, not a bar smeared over hundreds of writes.

    Goes to STDERR, with the rest of the narration. A sibling class used to paint a
    persistent per-model board on STDOUT with cursor-movement escapes, for callers that ran
    without a logger; there were none, and stdout is the CLIs' result channel."""

    def __init__(self, *, stream: TextIO | None = None, enabled: bool = True) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._enabled = bool(enabled) and getattr(self._stream, "isatty", lambda: False)()
        self._width = 0

    def update(self, text: str) -> None:
        if not self._enabled:
            return
        # Pad to the previous width so a shorter line cannot leave the tail of a longer
        # one behind it.
        padding = max(0, self._width - len(text))
        self._width = len(text)
        print(f"\r{text}{' ' * padding}", end="", file=self._stream, flush=True)

    def commit(self, text: str) -> None:
        """Freeze ``text`` as a durable line and start a fresh transient one below it."""
        if not self._enabled:
            return
        padding = max(0, self._width - len(text))
        print(f"\r{text}{' ' * padding}", file=self._stream, flush=True)
        self._width = 0

    def clear(self) -> None:
        if not self._enabled or not self._width:
            return
        print(f"\r{' ' * self._width}\r", end="", file=self._stream, flush=True)
        self._width = 0


@contextlib.contextmanager
def cli_progress_line(
    label: str,
    *,
    logger: CliLogger,
    fallback: str,
) -> Iterator[Callable[[ProgressEvent], None] | None]:
    """Paint a build as a sequence of phases: one durable line each, live one at the bottom.

    Yields None -- reporting nothing -- under ``--verbose``, where the logger is already
    narrating every stage and a bar repainting between its lines would fight with them. The
    status record is written regardless, so an open CAD Viewer still tracks the build.

    `scripts/artifact` builds exactly what `scripts/gen` builds and reported nothing while
    doing it -- the record went to the viewer, and a terminal caller watched a silent
    process. Sharing this is what stops the two disagreeing about whether a build is worth
    narrating."""
    if logger.verbose:
        yield None
        return
    line = InlineProgressLine(stream=logger.stream)
    # The phase currently on the live line: its name, its human label, and the wall clock at
    # which it started. Kept here rather than read back off the event because the event that
    # ENDS a phase is the one that opens the next, and its own start time is the boundary.
    state = {"phase": "", "label": "", "started": 0.0, "header": False}

    def paint(event: ProgressEvent) -> None:
        if not state["header"]:
            line.commit(label)
            state["header"] = True
        if event.phase != state["phase"]:
            if state["phase"] and state["started"]:
                line.commit(
                    _finished_phase_text(
                        str(state["label"]) or fallback,
                        event.phase_started_at_ms - float(state["started"]),
                    )
                )
            state.update(
                phase=event.phase, label=event.label, started=event.phase_started_at_ms
            )
        # The terminal event's only job here was to close the last phase's line, just done.
        if event.finished:
            return
        line.update(f"    {_progress_status_text(event, fallback=fallback)}")

    try:
        yield paint
    finally:
        line.clear()


def _format_elapsed(elapsed_ms: float) -> str:
    """A duration a human reads at a glance: ``259ms``, ``1.1s``, ``10m03s``."""
    milliseconds = max(0.0, float(elapsed_ms))
    seconds = milliseconds / 1000.0
    if seconds < 1.0:
        return f"{int(round(milliseconds))}ms"
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(round(seconds)), 60)
    return f"{minutes}m{remainder:02d}s"


def _finished_phase_text(label: str, elapsed_ms: float) -> str:
    """The durable line a phase leaves behind once it ends."""
    return f"  ✓ {label.lower():<26}{_format_elapsed(elapsed_ms):>9}"


def _progress_status_text(event: ProgressEvent, *, fallback: str) -> str:
    """The live line for the phase in flight.

    A phase that can count gets a bar and its real count (``312/1127``). One that cannot
    gets its label and, when it knows, the sub-unit it is working on -- which is a true
    statement about now, where a percentage would have been a guess about the end. Nothing
    here invents a denominator the build does not have."""
    if event.finished:
        return fallback
    text = (event.label or fallback).lower()
    fraction = event.fraction
    if fraction is not None:
        text = f"{text}  {render_progress_bar(fraction)}  {event.done}/{event.total}"
    if event.detail:
        text = f"{text}  {event.detail}"
    return text


