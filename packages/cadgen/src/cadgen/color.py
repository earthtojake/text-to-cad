"""Colour helpers for build123d part authoring.

The render pipeline treats a build123d ``Color``'s channels as **linear** RGB and
converts them to sRGB on the way to the screen
(``packages/cadgen-js/src/lib/assembly/meshData.js``, ``linearChannelToSrgbByte``).
So ``Color(0.5, 0.5, 0.5)`` does not display as ``#808080`` -- it displays as
roughly ``#BCBCBC``. Picking channel values off a hex palette by eye therefore
produces a washed-out, desaturated model, with no error to explain it.

Use :func:`srgb` to author the colour you actually want to see (it returns the
linear channel tuple, which ``shape.color = ...`` wraps into a ``Color``)::

    from cadgen.color import srgb

    part.color = srgb("#2E3742")        # the hex you picked in a design tool
    glass.color = srgb("#38414D", 0.42) # with alpha

Note also that colour set on a *group* compound never reaches the renderer --
only leaf occurrences carry colour into the tree. Style every leaf.
"""

from __future__ import annotations

__all__ = ["srgb", "srgb_to_linear", "linear_to_srgb"]


def srgb_to_linear(channel: float) -> float:
    """Convert one 0..1 sRGB channel to linear RGB."""
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> float:
    """Inverse of :func:`srgb_to_linear`, for reporting what a Color will look like."""
    if channel <= 0.0031308:
        return channel * 12.92
    return 1.055 * (channel ** (1 / 2.4)) - 0.055


def _parse_hex(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"expected a #rgb or #rrggbb colour, got {value!r}")
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"expected a hex colour, got {value!r}") from exc


def srgb(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """The linear RGBA channels for the sRGB hex you want to SEE on screen.

    ``value`` is ``#rgb`` or ``#rrggbb``. ``alpha`` is 0..1. Assign the result
    to ``shape.color``: build123d's setter wraps it in a ``Color`` whose
    channels are exactly these numbers.

    Returns a plain tuple, never a ``Color``, on purpose: a palette module that
    spells its constants ``CAST = srgb("#7f8288")`` runs at import, and
    constructing a ``Color`` there would import the CAD kernel (~2.5 s) before
    ``@step`` has had the chance to skip a current build or hand the run to the
    warm daemon. The kernel is touched only when a shape takes the colour.
    """
    red, green, blue = _parse_hex(value)
    return (
        srgb_to_linear(red / 255.0),
        srgb_to_linear(green / 255.0),
        srgb_to_linear(blue / 255.0),
        float(alpha),
    )
