"""One simulation result over its analysis's axis: a :class:`Waveform` and what it measures."""

from __future__ import annotations

import math
from typing import Any

from cadgen.kicad.design import DesignError
from cadgen.kicad.spice import to_number

__all__ = ["Waveform"]


class Waveform:
    """One result over an analysis's axis: ``x`` (seconds, hertz, or the swept value) and ``values``.

    Both are numpy arrays; ``values`` is complex for an AC run (use ``db``,
    ``magnitude`` and ``phase``). ``final`` is the last value, ``at(x)`` a
    linear interpolation (in log frequency for an AC run), ``crossings(level)``
    every axis value where the waveform crosses ``level``.
    """

    __slots__ = ("x", "values", "name", "unit", "axis", "axis_unit")

    def __init__(self, x: Any, values: Any, *, name: str, unit: str, axis: str, axis_unit: str):
        self.x = x
        self.values = values
        self.name = name
        self.unit = unit
        self.axis = axis
        self.axis_unit = axis_unit

    @property
    def is_complex(self) -> bool:
        import numpy

        return bool(numpy.iscomplexobj(self.values))

    def _real(self, what: str):
        if self.is_complex:
            raise DesignError(f"{self.name} is complex (an AC result): take {what} of .db, .magnitude or .phase")
        return self.values

    @staticmethod
    def _scalar(value: Any) -> float | complex:
        return complex(value) if isinstance(value, complex) else float(value)

    @property
    def final(self) -> float | complex:
        return self._scalar(self.values[-1])

    @property
    def initial(self) -> float | complex:
        return self._scalar(self.values[0])

    def max(self) -> float:
        return float(self._real("max()").max())

    def min(self) -> float:
        return float(self._real("min()").min())

    def _ordered(self):
        import numpy

        x, values = numpy.asarray(self.x, dtype=float), numpy.asarray(self.values)
        if len(x) > 1 and x[0] > x[-1]:
            x, values = x[::-1], values[::-1]
        return x, values

    def at(self, x: float) -> float | complex:
        """The value at axis position ``x``, interpolated linearly (log-frequency for AC)."""
        import numpy

        axis, values = self._ordered()
        position = to_number(x, what=f"{self.axis}")
        if not len(axis) or position < axis[0] or position > axis[-1]:
            raise DesignError(
                f"{self.name}.at({position:g}) is outside the run's {self.axis} "
                f"({axis[0]:g} to {axis[-1]:g} {self.axis_unit})" if len(axis) else f"{self.name} has no points"
            )
        if self.axis_unit == "Hz":
            axis, position = numpy.log10(axis), math.log10(position)
        if numpy.iscomplexobj(values):
            return complex(numpy.interp(position, axis, values.real), numpy.interp(position, axis, values.imag))
        return float(numpy.interp(position, axis, values))

    def crossings(self, level: float) -> list[float]:
        """Every axis value where the waveform crosses ``level`` (rising or falling), interpolated."""
        import numpy

        values = numpy.asarray(self._real("crossings()"), dtype=float) - to_number(level, what="level")
        x = numpy.asarray(self.x, dtype=float)
        found: list[float] = []
        logarithmic = self.axis_unit == "Hz"
        for index in range(len(values) - 1):
            a, b = values[index], values[index + 1]
            if a == 0:
                if not found or found[-1] != x[index]:
                    found.append(float(x[index]))
            elif a * b < 0:
                fraction = a / (a - b)
                if logarithmic:
                    found.append(float(10 ** (math.log10(x[index]) + fraction * (math.log10(x[index + 1]) - math.log10(x[index])))))
                else:
                    found.append(float(x[index] + fraction * (x[index + 1] - x[index])))
        if len(values) and values[-1] == 0 and (not found or found[-1] != x[-1]):
            found.append(float(x[-1]))
        return found

    @property
    def magnitude(self) -> "Waveform":
        import numpy

        return Waveform(self.x, numpy.abs(self.values), name=f"|{self.name}|", unit=self.unit, axis=self.axis, axis_unit=self.axis_unit)

    @property
    def db(self) -> "Waveform":
        """20 log10 of the magnitude: an AC transfer function's gain when the input is ``ac=1``."""
        import numpy

        with numpy.errstate(divide="ignore"):
            values = 20.0 * numpy.log10(numpy.abs(self.values))
        return Waveform(self.x, values, name=f"{self.name} dB", unit="dB", axis=self.axis, axis_unit=self.axis_unit)

    @property
    def phase(self) -> "Waveform":
        """The phase in degrees, unwrapped (it runs past +-180 rather than jumping)."""
        import numpy

        values = numpy.degrees(numpy.unwrap(numpy.angle(numpy.asarray(self.values, dtype=complex))))
        return Waveform(self.x, values, name=f"{self.name} phase", unit="deg", axis=self.axis, axis_unit=self.axis_unit)

    def __array__(self, dtype: Any = None, copy: Any = None):
        import numpy

        return numpy.asarray(self.values, dtype=dtype)

    def __len__(self) -> int:
        return len(self.values)

    def _combine(self, other: Any, operation: Any, symbol: str, reverse: bool = False) -> "Waveform":
        import numpy

        if isinstance(other, Waveform):
            if len(other.x) != len(self.x) or not numpy.array_equal(other.x, self.x):
                raise DesignError(f"{self.name} {symbol} {other.name}: the waveforms come from different runs")
            values, name = other.values, other.name
            unit = self.unit if other.unit == self.unit else ""
        elif isinstance(other, (int, float, complex)) and not isinstance(other, bool):
            values, name, unit = other, f"{other:g}", self.unit
        else:
            return NotImplemented
        left, right = (values, self.values) if reverse else (self.values, values)
        label = f"({name} {symbol} {self.name})" if reverse else f"({self.name} {symbol} {name})"
        return Waveform(self.x, operation(left, right), name=label, unit=unit if symbol in "+-" else "", axis=self.axis, axis_unit=self.axis_unit)

    def __add__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a + b, "+")

    def __radd__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a + b, "+", reverse=True)

    def __sub__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a - b, "-")

    def __rsub__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a - b, "-", reverse=True)

    def __mul__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a * b, "*")

    def __rmul__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a * b, "*", reverse=True)

    def __truediv__(self, other: Any) -> "Waveform":
        return self._combine(other, lambda a, b: a / b, "/")

    def __neg__(self) -> "Waveform":
        return Waveform(self.x, -self.values, name=f"-{self.name}", unit=self.unit, axis=self.axis, axis_unit=self.axis_unit)

    def __repr__(self) -> str:
        if not len(self.values):
            return f"Waveform({self.name}, empty)"
        final = self.final
        shown = f"{final.real:.6g}{final.imag:+.6g}j" if isinstance(final, complex) else f"{final:.6g}"
        return f"Waveform({self.name}, {len(self.values)} points over {self.axis}, final {shown} {self.unit})"
