"""How a real number reads in a STEP file cadgen writes: the one place that says it.

OCCT's writer prints a real within ``[0.1, 1000)`` in magnitude with twelve decimals and
cuts the text at fifteen characters (sign included), and any other real with thirteen
significant digits in exponent form; trailing zeros are dropped, and zero of either sign is
written ``0.``. A reader returns the nearest double to that text. Printing what was read
prints the same text again, so a number a reader takes from a file is stated as itself.
"""

from __future__ import annotations

import math

STEP_REAL_RANGE = (0.1, 1000.0)
STEP_REAL_RANGE_WIDTH = 15


def written_text(value: float) -> str:
    """The text cadgen's writer prints for the finite real ``value``."""
    if value == 0.0:
        return "0."
    if STEP_REAL_RANGE[0] <= abs(value) < STEP_REAL_RANGE[1]:
        return ("%.12f" % value)[:STEP_REAL_RANGE_WIDTH].rstrip("0")
    mantissa, exponent = ("%.12E" % value).split("E")
    return mantissa.rstrip("0") + "E" + exponent


def stated_real(value: float) -> float:
    """The number a STEP reader returns for ``value`` after cadgen's writer printed it
    (:func:`written_text`): the nearest double to that text. ValueError for a real that is
    not finite."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{value!r} is not a finite real")
    return float(written_text(value)) + 0.0
