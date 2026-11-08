"""A plane through a cadjoint field drawn as a PNG: ``section(scene, out, axis=, at=)``.

The plane ``axis = at`` is drawn with the other two axes across and up (``x``: y across, z up; ``y``: x
across, z up; ``z``: x across, y up). Inside the part (negative distance) is blue and outside orange,
each darker with distance and scaled on its own, so a 2 mm wall stays blue beside 30 mm of air; thin
lines are iso-distance contours every ``step`` millimetres and the thick black line is the surface,
distance zero. A mesh shows where the surface is; the field shows how far everything is from it: a
wall's thickness is twice the deepest distance inside it, a blend's reach shows from its seam, and a
feature finer than any mesh's cells still shows. The PNG is written with zlib alone.
"""

from __future__ import annotations

import math
import numbers
import os
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Section", "section"]

# (across, up) per slice axis.
AXES = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}
INSIDE = (38, 92, 168)
OUTSIDE = (226, 120, 38)
PAPER = (247, 247, 245)


@dataclass(frozen=True)
class Section:
    """What a section drew: the PNG (``path``); the plane (``"z = 0"``) and the axes across and up the
    picture; its extent in those axes' millimetres (``((u0, v0), (u1, v1))``); one pixel's size; the
    contours' spacing; the least and greatest distance in the plane (``field_range``, negative inside);
    and whether the plane crosses the surface at all."""

    path: Path
    plane: str
    across: str
    up: str
    extent: tuple[tuple[float, float], tuple[float, float]]
    pixel: float
    contour_step: float
    field_range: tuple[float, float]
    crosses_surface: bool


def _png(rgb: Any) -> bytes:
    """An (h, w, 3) uint8 array as the bytes of a PNG."""
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _write(out: Path, data: bytes) -> None:
    """``data`` at ``out`` whole or not at all: written beside it, then moved over it (law 17), by the
    library's one atomic replace (``cad._internal.atomic_replace``)."""
    from cad._internal.atomic_replace import write_bytes_atomic

    write_bytes_atomic(out, data)


def colour(distance: Any, pixel: float, step: float) -> Any:
    """The picture of a plane's distances: shaded by side and depth, contours every ``step``, the zero line.

    Inside and outside are scaled separately. A line is drawn where the field crosses a contour value
    within half a pixel, measured with the field's own gradient, so it stays one pixel wide where the
    field changes slowly (a cavity's medial axis) and is left out where it does not change at all: a
    plane along a wall's mid-plane reads one distance everywhere, and a contour there has no place."""
    import numpy as np

    inside = distance < 0
    depth = np.zeros_like(distance)
    if inside.any():
        depth[inside] = -distance[inside] / max(float(-distance.min()), 1e-12)
    if (~inside).any():
        depth[~inside] = distance[~inside] / max(float(distance.max()), 1e-12)
    depth = np.clip(depth, 0.0, 1.0)[..., None] ** 0.6
    tint = np.where(inside[..., None], np.asarray(INSIDE), np.asarray(OUTSIDE))
    rgb = np.asarray(PAPER) * (1 - 0.8 * depth) + tint * 0.8 * depth

    gy, gx = np.gradient(distance, pixel)
    gradient = np.hypot(gx, gy)
    slope = np.maximum(gradient, 1e-3) * pixel  # the field's change across one pixel
    offset = distance / step - np.round(distance / step)
    varies = gradient > 0.05
    contour = varies & (np.abs(offset) * step < 0.5 * slope) & (np.abs(distance) > slope)
    rgb[contour] = rgb[contour] * 0.55
    rgb[np.abs(distance) < 1.2 * slope] = (0, 0, 0)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value):
        raise ValueError(f"{what} is a finite number, not {value!r}")
    return float(value)


def section(scene: Any, out: str | os.PathLike, *, axis: str = "z", at: float = 0.0, step: float | None = None,
            pixels: int = 900, bounds: Sequence[float] | None = None) -> Section:
    """The plane ``axis = at`` through the cadjoint field ``scene``, drawn into ``out`` (a ``.png``), and
    what it shows (``Section``).

    ``axis`` is ``"x"``, ``"y"`` or ``"z"``; ``at`` the plane's place along it, in millimetres. ``step`` is
    the contours' spacing (by default a twentieth of the extent, to a tenth of a millimetre); ``pixels``
    the longer side's pixels, 64 to 4096. The extent is the part's, from cadjoint's ``fit_bounds``, unless
    ``bounds=(u0, v0, u1, v1)`` gives it in the plane's across and up millimetres. The field is evaluated
    once, at every pixel's centre; nothing is meshed. ``out`` is written whole or not at all.

    Refused with a ``ValueError``: an axis other than the three, pixels outside 64 to 4096, a step that is
    not above zero, bounds that are not u0 < u1 and v0 < v1, an ``out`` that is no ``.png``; and a field
    with no closed part in reach and no bounds. A ``TypeError`` for a ``scene`` that is no cadjoint field.
    """
    import numpy as np

    from cad.cadjoint._field import _fitted, _scene

    field = _scene(scene, "cad.cadjoint.section")
    if axis not in AXES:
        raise ValueError(f"axis is one of x, y, z, not {axis!r}")
    if isinstance(pixels, bool) or not isinstance(pixels, numbers.Integral) or not 64 <= pixels <= 4096:
        raise ValueError(f"pixels is a whole number from 64 to 4096, not {pixels!r}")
    at = _number(at, "at")
    if step is not None and _number(step, "step") <= 0:
        raise ValueError(f"step is the contours' spacing in millimetres, above zero, not {step!r}")
    path = Path(os.fspath(out))
    if path.suffix.lower() != ".png":
        raise ValueError(f"a section is drawn into a .png, not {path.name}")
    across, up = AXES[axis]
    if bounds is None:
        origin, extent = _fitted(field, "cad.cadjoint.section")
        u0, v0 = origin[across], origin[up]
        u1, v1 = u0 + extent[across], v0 + extent[up]
    else:
        try:
            u0, v0, u1, v1 = (_number(value, "a bound") for value in bounds)
        except (TypeError, ValueError):
            raise ValueError(f"bounds is (u0, v0, u1, v1), four finite numbers in millimetres, not {bounds!r}") from None
        if u1 <= u0 or v1 <= v0:
            raise ValueError(f"bounds needs u0 < u1 and v0 < v1 (U0 < U1 and V0 < V1), not {tuple(bounds)!r}")
    pixel = max(u1 - u0, v1 - v0) / pixels
    width = max(1, round((u1 - u0) / pixel))
    height = max(1, round((v1 - v0) / pixel))
    u = u0 + (np.arange(width) + 0.5) * pixel
    v = v1 - (np.arange(height) + 0.5) * pixel  # the picture's rows run downward
    uu, vv = np.meshgrid(u, v)
    points = np.zeros((height, width, 3), dtype=np.float32)
    points[..., across] = uu
    points[..., up] = vv
    points[..., "xyz".index(axis)] = at
    distance = np.asarray(field(points.reshape(-1, 3)), dtype=np.float64).reshape(height, width)
    if not np.isfinite(distance).all():
        raise ValueError("the field is not finite everywhere on the plane (NaN or infinite): no section is drawn of it")
    contour = float(step) if step is not None else (float(np.round(max(u1 - u0, v1 - v0) / 20.0, 1)) or pixel * 10)
    _write(path, _png(colour(distance, pixel, contour)))
    return Section(path=path.resolve(), plane=f"{axis} = {at:g}", across="xyz"[across], up="xyz"[up],
                   extent=((u0, v0), (u1, v1)), pixel=pixel, contour_step=contour,
                   field_range=(float(distance.min()), float(distance.max())),
                   crosses_surface=bool(distance.min() < 0 < distance.max()))
