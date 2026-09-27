"""Read a PNG's pixels with nothing but the standard library.

A render test that asserts "the stroke is here and the background is there" has
to decode the image cadgen just wrote. Pillow would do it, but it is not one of
this repo's declared dependencies, and a test may not depend on a package that
happens to be installed — so the 60 lines are here instead.

Scope is exactly what a browser's ``canvas.toDataURL("image/png")`` produces:
8 bits per channel, colour type 2 (RGB) or 6 (RGBA), no interlacing. Anything
else raises by name rather than being decoded approximately.
"""

from __future__ import annotations

import struct
import zlib

__all__ = ["PngImage", "read_png"]

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {2: 3, 6: 4}


class PngImage:
    """One decoded image: ``width``, ``height`` and ``pixel(x, y) -> (r, g, b)``."""

    __slots__ = ("width", "height", "_channels", "_rows")

    def __init__(self, width: int, height: int, channels: int, rows: bytearray) -> None:
        self.width = width
        self.height = height
        self._channels = channels
        self._rows = rows

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """The RGB at ``(x, y)``, with the origin at the top left. Alpha is dropped."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"({x}, {y}) is outside a {self.width}x{self.height} image")
        start = (y * self.width + x) * self._channels
        return tuple(self._rows[start : start + 3])  # type: ignore[return-value]


def _unfilter(data: bytes, width: int, height: int, channels: int) -> bytearray:
    """Undo the per-scanline filters (PNG spec §9). One byte of filter type per row."""
    stride = width * channels
    out = bytearray(stride * height)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        filter_type = data[position]
        position += 1
        line = bytearray(data[position : position + stride])
        position += stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            value = line[index]
            if filter_type == 0:
                pass
            elif filter_type == 1:
                value += left
            elif filter_type == 2:
                value += up
            elif filter_type == 3:
                value += (left + up) // 2
            elif filter_type == 4:
                # Paeth: the neighbour closest to left + up - upper_left.
                estimate = left + up - upper_left
                distances = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - upper_left),
                )
                value += (left, up, upper_left)[distances.index(min(distances))]
            else:
                raise ValueError(f"PNG row {row} uses unknown filter type {filter_type}")
            line[index] = value & 0xFF
        out[row * stride : (row + 1) * stride] = line
        previous = line
    return out


def read_png(data: bytes) -> PngImage:
    """Decode 8-bit RGB/RGBA PNG bytes."""
    if not data.startswith(_SIGNATURE):
        raise ValueError("not a PNG: the 8-byte signature is missing")
    width = height = bit_depth = color_type = interlace = 0
    compressed = bytearray()
    position = len(_SIGNATURE)
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        position += 12 + length  # length + type + body + CRC
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", body
            )
        elif kind == b"IDAT":
            compressed += body
        elif kind == b"IEND":
            break
    if bit_depth != 8 or color_type not in _CHANNELS or interlace != 0:
        raise ValueError(
            f"this reader handles 8-bit non-interlaced RGB/RGBA PNGs; got bit depth "
            f"{bit_depth}, colour type {color_type}, interlace {interlace}"
        )
    channels = _CHANNELS[color_type]
    return PngImage(width, height, channels, _unfilter(zlib.decompress(bytes(compressed)), width, height, channels))
