"""Colours as the author sees them, and as the document holds them.

An author gives a colour in sRGB, the space a colour picker shows: a hex string (``"#e68019"``,
``"#e68019cc"``, ``"#e81"``, ``"#e81c"``), a tuple of 0-255 integers (``(230, 128, 25)``, or four
with alpha), or a build123d ``Color``, whose channels build123d defines as sRGB (its constructor
and its iteration are ``Quantity_TOC_sRGB``). The document holds linear RGB, as OCCT's
``Quantity_Color`` and glTF's factors do: ``linear`` converts at the door, so ``shape.color =
"#e68019"`` and ``paint(shape, faces, "#e68019")`` store the very same colour. ``color`` is the way
back: a build123d ``Color`` of a linear colour the document holds, for a shape a reader makes.

A converted channel is rounded to six decimals, the precision a document's colour is read back
at, so a colour read back is the colour written (a step of 8-bit sRGB is ~1e-3). ``Linear``
marks a colour that is linear already: what the engine reads from a document and gives back
to a ``Material``. An author never writes one.

Importing this module imports no kernel.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Linear", "color", "linear", "linear_to_srgb", "srgb_to_linear"]


class Linear(tuple):
    """Linear RGB(A) channels in 0-1, as the document holds them."""

    __slots__ = ()


def srgb_to_linear(channel: float) -> float:
    """One 0-1 sRGB channel as linear RGB (IEC 61966-2-1)."""
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> float:
    """One 0-1 linear channel as sRGB: the inverse of ``srgb_to_linear``."""
    if channel <= 0.0031308:
        return channel * 12.92
    return 1.055 * (channel ** (1 / 2.4)) - 0.055


def _takes(what: str, alpha: bool) -> str:
    if alpha:
        return (f"{what} is a hex string ('#rrggbb', '#rrggbbaa', '#rgb', '#rgba'), 0-255 integers (r, g, b) or "
                f"(r, g, b, a), or a build123d Color")
    return f"{what} is a hex string ('#rrggbb', '#rgb'), 0-255 integers (r, g, b), or a build123d Color"


def _hex(value: str, what: str, alpha: bool) -> tuple[int, ...]:
    text = value.strip()
    digits = text[1:] if text.startswith("#") else ""
    sizes = (3, 4, 6, 8) if alpha else (3, 6)
    if len(digits) not in sizes or any(ch not in "0123456789abcdefABCDEF" for ch in digits):
        raise ValueError(f"{_takes(what, alpha)}, not {value!r}")
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits)
    return tuple(int(digits[at:at + 2], 16) for at in range(0, len(digits), 2))


def _bytes(value: Any, what: str, alpha: bool) -> tuple[int, ...]:
    try:
        items = tuple(value)
    except TypeError:
        raise ValueError(f"{_takes(what, alpha)}, not {value!r}") from None
    if len(items) not in ((3, 4) if alpha else (3,)) or \
            any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255 for item in items):
        raise ValueError(f"{_takes(what, alpha)}, not {value!r}")
    return items


def _is_build123d_color(value: Any) -> bool:
    # By its shape, not its class: this module imports no kernel.
    wrapped = getattr(value, "wrapped", None)
    return type(value).__name__ == "Color" and hasattr(wrapped, "GetRGB") and hasattr(wrapped, "Alpha")


def linear(value: Any, what: str = "a colour", *, alpha: bool = True) -> Linear:
    """``value`` (see the module) as linear RGBA, or RGB when not ``alpha``; a ``ValueError``
    naming ``what`` and what it takes for anything else."""
    if isinstance(value, Linear):
        channels = tuple(float(item) for item in value)
        if len(channels) not in ((3, 4) if alpha else (3,)) or not all(0.0 <= item <= 1.0 for item in channels):
            raise ValueError(f"{what}: linear channels out of range: {value!r}")
        return Linear((*channels, 1.0) if alpha and len(channels) == 3 else channels)
    if _is_build123d_color(value):
        rgb = value.wrapped.GetRGB()
        channels = tuple(round(float(item), 6) for item in (rgb.Red(), rgb.Green(), rgb.Blue()))
        return Linear((*channels, round(float(value.wrapped.Alpha()), 6)) if alpha else channels)
    if isinstance(value, str):
        given = _hex(value, what, alpha)
    elif isinstance(value, (bytes, bytearray)):
        raise ValueError(f"{_takes(what, alpha)}, not {value!r}")
    else:
        given = _bytes(value, what, alpha)
    channels = tuple(round(srgb_to_linear(item / 255.0), 6) for item in given[:3])
    if not alpha:
        return Linear(channels)
    return Linear((*channels, round(given[3] / 255.0, 6) if len(given) == 4 else 1.0))


def color(rgba: Any) -> Any:
    """A build123d ``Color`` holding the linear ``rgba`` the document holds (alpha 1 when three
    channels are given)."""
    from build123d import Color
    from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TypeOfColor

    channels = tuple(float(item) for item in rgba)
    held = Quantity_Color(channels[0], channels[1], channels[2], Quantity_TypeOfColor.Quantity_TOC_RGB)
    return Color(Quantity_ColorRGBA(held, channels[3] if len(channels) > 3 else 1.0))
