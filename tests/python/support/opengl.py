"""What a test that draws does where no OpenGL context can be made.

It skips, saying why -- a machine with no GPU driver (Windows' GDI 1.1 draws nothing) or no X
display. On CI with an X display it fails instead: the job set the display up (Xvfb, Mesa) for
exactly these tests, so a context it cannot make is a fault, and a drawing suite that skipped
itself there would be a test no job runs. A test whose other steps run anywhere asks ``draws``
instead, and leaves out its drawing step alone where ``require`` would skip. Each takes
``render.context.available()``'s answer, so this package imports no cadgen."""

from __future__ import annotations

import os
import unittest


def require(reason: str | None, what: str = "no OpenGL context") -> None:
    """Nothing when ``reason`` is None; else skip -- or, on CI with a DISPLAY, fail -- naming it."""
    if reason is None:
        return
    display = os.environ.get("DISPLAY")
    if os.environ.get("CI") and display:
        raise AssertionError(f"{what} on CI, whose display {display} was set up to draw: {reason}")
    raise unittest.SkipTest(f"{what}: {reason}")


def draws(reason: str | None, what: str = "no OpenGL context") -> bool:
    """Whether a test's drawing step runs here, for a test whose other steps run anywhere: True when
    ``reason`` is None; False where ``require`` would skip; on CI with a DISPLAY, ``require``'s failure."""
    try:
        require(reason, what)
    except unittest.SkipTest:
        return False
    return True
