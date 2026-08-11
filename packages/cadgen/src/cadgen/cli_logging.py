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
            self.info(f"{label} completed in {format_elapsed(elapsed)}")

    @contextmanager
    def timed(self, label: str) -> Iterator[None]:
        started_at = time.perf_counter()
        self.debug(f"{label} started")
        try:
            yield
        finally:
            self.timing(label, time.perf_counter() - started_at)

    def total(self, label: str = "total") -> None:
        self.timing(label, time.perf_counter() - self._started_at)

    def _line(self, message: str) -> str:
        return f"[{self.name}] {message}"
