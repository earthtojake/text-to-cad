"""What a plan says on stderr while it runs: nothing unless asked (``verbose``), then each stage and its time.

``cadgen cam plan --verbose`` reads the stages back to say where a slow plan spent its time; the result's ``timings``
carry the same numbers for a library caller. Stdlib only.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

__all__ = ["CamLog"]


def _elapsed(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000.0:.0f}ms"
    if seconds < 60.0:
        return f"{seconds:.2f}s"
    minutes, rest = divmod(seconds, 60.0)
    return f"{int(minutes)}m {rest:.1f}s"


class CamLog:
    """``[cam] ...`` lines on ``stream`` (stderr), written only when ``verbose``."""

    def __init__(self, *, verbose: bool = False, stream: TextIO | None = None) -> None:
        self.verbose = verbose
        self.stream = stream

    def debug(self, message: str) -> None:
        if self.verbose:
            print(f"[cam] {message}", file=self.stream or sys.stderr)

    @contextmanager
    def timed(self, label: str) -> Iterator[None]:
        started = time.perf_counter()
        self.debug(f"{label} started")
        try:
            yield
        finally:
            self.debug(f"{label} completed in {_elapsed(time.perf_counter() - started)}")
