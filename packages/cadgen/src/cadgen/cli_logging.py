from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import sys
import time
from typing import Iterator, TextIO


def format_elapsed(seconds: float) -> str:
    milliseconds = seconds * 1000.0
    if milliseconds < 1000.0:
        return f"{milliseconds:.0f}ms"
    if seconds < 60.0:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60.0)
    return f"{int(minutes)}m {remainder:.1f}s"


@dataclass
class CliLogger:
    name: str
    verbose: bool = False
    stream: TextIO | None = None
    _started_at: float = field(default_factory=time.perf_counter)
    _open_stages: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stream is None:
            self.stream = sys.stderr

    def info(self, message: str) -> None:
        print(self._line(message), file=self.stream)

    def warning(self, message: str) -> None:
        print(self._line(f"warning: {message}"), file=self.stream)

    def debug(self, message: str) -> None:
        if self.verbose:
            self.info(message)

    def timing(self, label: str, elapsed: float) -> None:
        if self.verbose:
            # Peak RSS so far rides every stage line: a build report then says
            # where memory went, not just where time went (the w16 engine's
            # overnight OOMs left logs with no memory numbers at all).
            self.info(f"{label} completed in {format_elapsed(elapsed)}")

    def current_stage(self) -> str:
        """The innermost ``timed`` label still open, for the memory guard's message."""
        return self._open_stages[-1] if self._open_stages else ""

    @contextmanager
    def timed(self, label: str) -> Iterator[None]:
        started_at = time.perf_counter()
        self.debug(f"{label} started")
        self._open_stages.append(label)
        try:
            yield
        finally:
            self._open_stages.pop()
            self.timing(label, time.perf_counter() - started_at)

    def total(self, label: str = "total") -> None:
        self.timing(label, time.perf_counter() - self._started_at)

    def _line(self, message: str) -> str:
        return f"[{self.name}] {message}"
