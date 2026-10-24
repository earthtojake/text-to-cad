"""PROTOTYPE: the viewer's words as pictures, drawn the way the viewer's page draws them, for the
OCCT renderer to lay on a quad or over the frame.

The viewer writes a text mark's words onto a 2D canvas and maps the canvas onto the mark's quad
(``annotation.js`` ``textCanvas``): ``500 <2 x fontPx>px ui-sans-serif, system-ui, sans-serif``,
``textBaseline = "top"``, lines 1.25 apart, the canvas ``ceil(widest line) + 2`` by
``ceil(lines x fontPx x 1.25 x 2) + 2`` with the words at (1, 1). Measure's label is the same
face at 600 (``measureDimension.js``). Chromium has no ``ui-sans-serif``; its ``system-ui`` is the
platform's UI face, and so is this module's (``face_source``):

- **macOS**: San Francisco, the variable ``/System/Library/Fonts/SFNS.ttf``, set as Chromium sets
  it there (``measureText`` to within 0.05 px a line): the weight axis at the CSS weight, the
  optical size at the font size, its kerning and its size tracking (``trak``), and macOS's font
  smoothing, which Chromium's canvas text keeps (each side of an outline grown by
  ``0.00605 x size`` px, at most 0.3, none from 72 px up), on a whole-pixel baseline.
- **Windows**: Segoe UI (``SegUIVar.ttf``, the variable one, else ``segoeui.ttf`` and, from 600,
  ``seguisb.ttf``).
- **Linux**: what fontconfig gives for ``sans-serif`` at the weight (DejaVu Sans, Liberation
  Sans, ...).
- **Else**: Pillow's own scalable face (``ImageFont.load_default``), so words always draw.

The fonts are read with Pillow (FreeType: outlines, advances at the font's units, a variable
font's instance) and ``struct`` (the tables Pillow does not read: the character map, the variation
axes, GPOS's kern pairs with their variation deltas, ``trak``); nothing else. Glyphs sit at
fractional x positions and are rasterised at ten times the size and averaged down. Fitted against
Chromium's canvas on macOS at the viewer's sizes (32, 40 and 56 px: Annotate's 16, 20 and 28 at
twice), the coverage differs by 1.4 to 2.1 levels in 255 on average, the ink by under 3%. Not
done: substitutions (GSUB ligatures and contextual alternates), and scripts other than the face's
simple ones.
"""

from __future__ import annotations

import bisect
import math
import os
import struct
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from cadgen.engine import executables
from typing import Any

import numpy as np

TEXT_SCALE = 2  # the viewer's text canvas is twice the words' size (annotation.js textCanvas)
LINE_HEIGHT = 1.25
SUPERSAMPLE = 10
MAX_TEXT_RASTER = 256_000_000  # a text mark's supersampled canvas (px); any real label is far smaller
MAC_FACE = Path("/System/Library/Fonts/SFNS.ttf")
# How far FreeType's ink sits from CoreText's for the same baseline, fitted on macOS: up a fifth
# of a pixel.
MAC_BASELINE_SHIFT = -0.2
PILLOW_DEFAULT = "Pillow's default face"


# --- which face ------------------------------------------------------------------------------


@lru_cache(maxsize=8)
def face_source(weight: float) -> tuple[str | None, str]:
    """The platform's UI face for a CSS weight: (its file, or None for Pillow's own; its name)."""
    if sys.platform == "darwin" and MAC_FACE.is_file():
        return str(MAC_FACE), MAC_FACE.name
    if sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in (["SegUIVar.ttf"] + (["seguisb.ttf"] if weight >= 600 else []) + ["segoeui.ttf"]):
            if (fonts / name).is_file():
                return str(fonts / name), name
    elif fc_match := executables.find("fc-match"):  # by its absolute path: never the working folder's
        # fontconfig's weights: regular 80, medium 100, demibold 180, bold 200.
        fc = 80 if weight < 450 else 100 if weight < 550 else 180 if weight < 650 else 200
        try:
            found = subprocess.run([fc_match, "-f", "%{file}", f"sans-serif:weight={fc}"], capture_output=True,
                                   text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            found = ""
        if found and Path(found).is_file() and Path(found).suffix.lower() in (".ttf", ".otf", ".ttc"):
            return found, Path(found).name
    return None, PILLOW_DEFAULT


# --- the tables Pillow does not read -----------------------------------------------------------


class OpenType:
    """An OpenType font's units, metrics, character map, variation axes and normalisation, GDEF's
    variation store, GPOS's kern pairs and ``trak``'s normal track, read with ``struct``."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        start = struct.unpack_from(">I", data, 12)[0] if data[:4] == b"ttcf" else 0  # a collection's first
        count = struct.unpack_from(">H", data, start + 4)[0]
        self.tables = {}
        for index in range(count):
            tag, _check, offset, length = struct.unpack_from(">4sIII", data, start + 12 + 16 * index)
            self.tables[tag.decode("latin-1")] = offset
        self.upm = self.u16(self.tables["head"] + 18)
        hhea = self.tables["hhea"]
        self.ascent, self.descent = self.i16(hhea + 4), -self.i16(hhea + 6)
        self.axes = self._axes()
        self.maps = self._avar()
        self._cmap = self._character_map()
        self._glyphs: dict[str, int] = {}

    def u16(self, at: int) -> int:
        return struct.unpack_from(">H", self.data, at)[0]

    def i16(self, at: int) -> int:
        return struct.unpack_from(">h", self.data, at)[0]

    def u32(self, at: int) -> int:
        return struct.unpack_from(">I", self.data, at)[0]

    # -- characters --

    def _character_map(self) -> tuple[int, int] | None:
        if "cmap" not in self.tables:
            return None
        base = self.tables["cmap"]
        found = None
        for index in range(self.u16(base + 2)):
            platform, encoding, offset = struct.unpack_from(">HHI", self.data, base + 4 + 8 * index)
            kind = self.u16(base + offset)
            unicode = platform == 0 or (platform == 3 and encoding in (1, 10))
            if unicode and kind == 12:
                return 12, base + offset
            if unicode and kind == 4 and found is None:
                found = (4, base + offset)
        return found

    def glyph(self, char: str) -> int:
        cached = self._glyphs.get(char)
        if cached is not None:
            return cached
        found, code = 0, ord(char)
        if self._cmap is not None:
            kind, at = self._cmap
            if kind == 12:
                groups = self.u32(at + 12)
                low, high = 0, groups - 1
                while low <= high:
                    middle = (low + high) // 2
                    first, last, start = struct.unpack_from(">III", self.data, at + 16 + 12 * middle)
                    if code < first:
                        high = middle - 1
                    elif code > last:
                        low = middle + 1
                    else:
                        found = start + code - first
                        break
            elif code <= 0xFFFF:
                segments = self.u16(at + 6) // 2
                ends = at + 14
                starts, deltas = ends + 2 * segments + 2, ends + 4 * segments + 2
                ranges = ends + 6 * segments + 2
                index = bisect.bisect_left([self.u16(ends + 2 * i) for i in range(segments)], code)
                if index < segments and self.u16(starts + 2 * index) <= code:
                    first, delta, offset = self.u16(starts + 2 * index), self.i16(deltas + 2 * index), self.u16(ranges + 2 * index)
                    if offset == 0:
                        found = (code + delta) & 0xFFFF
                    else:
                        value = self.u16(ranges + 2 * index + offset + 2 * (code - first))
                        found = (value + delta) & 0xFFFF if value else 0
        self._glyphs[char] = found
        return found

    # -- variations --

    def _axes(self) -> list[tuple[str, float, float, float]]:
        if "fvar" not in self.tables:
            return []
        base = self.tables["fvar"]
        first, count, size = self.u16(base + 4), self.u16(base + 8), self.u16(base + 10)
        axes = []
        for index in range(count):
            at = base + first + index * size
            low, default, high = (value / 65536 for value in struct.unpack_from(">iii", self.data, at + 4))
            axes.append((self.data[at:at + 4].decode("latin-1"), low, default, high))
        return axes

    def _avar(self) -> dict[str, list[tuple[float, float]]]:
        if "avar" not in self.tables or not self.axes:
            return {}
        at, maps = self.tables["avar"] + 8, {}
        for tag, *_range in self.axes:
            count = self.u16(at)
            maps[tag] = [(self.i16(at + 2 + 4 * k) / 16384, self.i16(at + 4 + 4 * k) / 16384) for k in range(count)]
            at += 2 + 4 * count
        return maps

    def location(self, wanted: dict[str, float]) -> list[float]:
        """The axes' values in the font's order (``wanted`` clamped to each axis, else its default)."""
        return [min(max(float(wanted.get(tag, default)), low), high) for tag, low, default, high in self.axes]

    def normalised(self, values: list[float]) -> list[float]:
        found = []
        for (tag, low, default, high), value in zip(self.axes, values):
            n = (value - default) / (default - low) if value < default and default > low else \
                (value - default) / (high - default) if value > default and high > default else 0.0
            pairs = self.maps.get(tag)
            if pairs:
                for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
                    if x0 <= n <= x1:
                        n = y0 if x1 == x0 else y0 + (y1 - y0) * (n - x0) / (x1 - x0)
                        break
            found.append(n)
        return found

    @lru_cache(maxsize=8)
    def _store(self) -> tuple[list[list[tuple[float, float, float]]], list[tuple[list[int], list[list[int]]]]] | None:
        """GDEF's item variation store: its regions and its delta sets (region indexes, rows)."""
        if "GDEF" not in self.tables:
            return None
        base = self.tables["GDEF"]
        if (self.u16(base), self.u16(base + 2)) < (1, 3) or not self.u32(base + 14):
            return None
        store = base + self.u32(base + 14)
        regions_at = store + self.u32(store + 2)
        axis_count, region_count = self.u16(regions_at), self.u16(regions_at + 2)
        regions = [[tuple(self.i16(regions_at + 4 + (r * axis_count + a) * 6 + 2 * k) / 16384 for k in range(3))
                    for a in range(axis_count)] for r in range(region_count)]
        sets = []
        for index in range(self.u16(store + 6)):
            at = store + self.u32(store + 8 + 4 * index)
            items, words, indexes = self.u16(at), self.u16(at + 2), self.u16(at + 4)
            long, words = bool(words & 0x8000), words & 0x7FFF
            used = [self.u16(at + 6 + 2 * k) for k in range(indexes)]
            row_at, rows = at + 6 + 2 * indexes, []
            big, small = (">i", ">h") if long else (">h", ">b")
            big_size, small_size = (4, 2) if long else (2, 1)
            for _item in range(items):
                row = []
                for column in range(indexes):
                    form, size = (big, big_size) if column < words else (small, small_size)
                    row.append(struct.unpack_from(form, self.data, row_at)[0])
                    row_at += size
                rows.append(row)
            sets.append((used, rows))
        return regions, sets

    def delta(self, outer: int, inner: int, coords: tuple[float, ...]) -> float:
        store = self._store()
        if store is None:
            return 0.0
        regions, sets = store
        if outer >= len(sets) or inner >= len(sets[outer][1]):
            return 0.0
        used, rows = sets[outer]
        total = 0.0
        for region_index, value in zip(used, rows[inner]):
            scalar = 1.0
            for (start, peak, end), coord in zip(regions[region_index], coords):
                if peak == 0 or start > peak or peak > end or (start < 0 < end):
                    continue
                if coord < start or coord > end:
                    scalar = 0.0
                    break
                if coord != peak:
                    scalar *= (coord - start) / (peak - start) if coord < peak else (end - coord) / (end - peak)
            total += scalar * value
        return total

    # -- kerning --

    @lru_cache(maxsize=8)
    def _kern_tables(self) -> list[list[int]]:
        """GPOS's ``kern`` lookups (Latin's, else the default script's), each its pair subtables."""
        if "GPOS" not in self.tables:
            return []
        base = self.tables["GPOS"]
        scripts, features, lookups = (base + self.u16(base + 4 + 2 * k) for k in range(3))
        system = None
        for index in range(self.u16(scripts)):
            tag, offset = self.data[scripts + 2 + 6 * index:scripts + 6 + 6 * index], self.u16(scripts + 6 + 6 * index)
            if tag in (b"latn", b"DFLT") and (system is None or tag == b"latn"):
                system = scripts + offset
        if system is None or not self.u16(system):
            return []
        language = system + self.u16(system)
        chosen = []
        for k in range(self.u16(language + 4)):
            feature = self.u16(language + 6 + 2 * k)
            record = features + 2 + 6 * feature
            if self.data[record:record + 4] == b"kern":
                table = features + self.u16(record + 4)
                chosen += [self.u16(table + 4 + 2 * j) for j in range(self.u16(table + 2))]
        found = []
        for index in sorted(set(chosen)):
            lookup = lookups + self.u16(lookups + 2 + 2 * index)
            kind, count = self.u16(lookup), self.u16(lookup + 4)
            subtables = []
            for j in range(count):
                sub = lookup + self.u16(lookup + 6 + 2 * j)
                if kind == 9:
                    if self.u16(sub + 2) != 2:
                        continue
                    sub += self.u32(sub + 4)
                elif kind != 2:
                    continue
                subtables.append(sub)
            found.append(subtables)
        return found

    def _covered(self, coverage: int, glyph: int) -> int | None:
        if self.u16(coverage) == 1:
            count = self.u16(coverage + 2)
            glyphs = [self.u16(coverage + 4 + 2 * k) for k in range(count)]
            index = bisect.bisect_left(glyphs, glyph)
            return index if index < count and glyphs[index] == glyph else None
        for k in range(self.u16(coverage + 2)):
            first, last, start = struct.unpack_from(">HHH", self.data, coverage + 4 + 6 * k)
            if first <= glyph <= last:
                return start + glyph - first
        return None

    def _class(self, table: int, glyph: int) -> int:
        if self.u16(table) == 1:
            first, count = self.u16(table + 2), self.u16(table + 4)
            return self.u16(table + 6 + 2 * (glyph - first)) if first <= glyph < first + count else 0
        for k in range(self.u16(table + 2)):
            first, last, kind = struct.unpack_from(">HHH", self.data, table + 4 + 6 * k)
            if first <= glyph <= last:
                return kind
        return 0

    def _advance(self, base: int, at: int, form: int, coords: tuple[float, ...]) -> float:
        """A value record's x advance (with its variation delta) at ``at``, of value format ``form``;
        its device offsets count from ``base`` (a pair set's own table, or the subtable)."""
        value, field = 0.0, at
        for bit in range(8):
            if not form & (1 << bit):
                continue
            if bit == 2:
                value += self.i16(field)
            elif bit == 6 and self.u16(field):
                device = base + self.u16(field)
                if self.u16(device + 4) == 0x8000:  # a variation index
                    value += self.delta(self.u16(device), self.u16(device + 2), coords)
            field += 2
        return value

    def kern(self, left: int, right: int, coords: tuple[float, ...]) -> float:
        """The kern pair's x advance adjustment of ``left`` before ``right``, in font units."""
        total = 0.0
        for subtables in self._kern_tables():
            for sub in subtables:
                at = self._covered(sub + self.u16(sub + 2), left)
                if at is None:
                    continue
                form1, form2 = self.u16(sub + 4), self.u16(sub + 6)
                size1, size2 = 2 * bin(form1).count("1"), 2 * bin(form2).count("1")
                if self.u16(sub) == 1:
                    pairs = sub + self.u16(sub + 10 + 2 * at)
                    count, step = self.u16(pairs), 2 + size1 + size2
                    seconds = [self.u16(pairs + 2 + step * k) for k in range(count)]
                    index = bisect.bisect_left(seconds, right)
                    if index == count or seconds[index] != right:
                        continue
                    total += self._advance(pairs, pairs + 2 + step * index + 2, form1, coords)
                else:
                    first = self._class(sub + self.u16(sub + 8), left)
                    second = self._class(sub + self.u16(sub + 10), right)
                    classes2 = self.u16(sub + 14)
                    record = sub + 16 + (first * classes2 + second) * (size1 + size2)
                    total += self._advance(sub, record, form1, coords)
                break  # a lookup's first subtable to take the pair is its only one
        return total

    # -- tracking --

    def track(self, size: float) -> float:
        """``trak``'s normal track at ``size``, in font units (0 without one)."""
        if "trak" not in self.tables:
            return 0.0
        base = self.tables["trak"]
        horizontal = self.u16(base + 6)
        if not horizontal:
            return 0.0
        data = base + horizontal
        tracks, sizes, sizes_at = self.u16(data), self.u16(data + 2), base + self.u32(data + 4)
        points = [struct.unpack_from(">i", self.data, sizes_at + 4 * k)[0] / 65536 for k in range(sizes)]
        for k in range(tracks):
            entry = data + 8 + 8 * k
            if struct.unpack_from(">i", self.data, entry)[0] == 0:
                values = [self.i16(base + self.u16(entry + 6) + 2 * j) for j in range(sizes)]
                if size <= points[0]:
                    return float(values[0])
                if size >= points[-1]:
                    return float(values[-1])
                index = bisect.bisect_right(points, size)
                low, high = points[index - 1], points[index]
                return values[index - 1] + (values[index] - values[index - 1]) * (size - low) / (high - low)
        return 0.0


@lru_cache(maxsize=8)
def _opentype(path: str) -> OpenType:
    return OpenType(Path(path).read_bytes())


@lru_cache(maxsize=64)
def _pillow_font(path: str | None, size: float, values: tuple[float, ...]) -> Any:
    from PIL import ImageFont

    if path is None:
        return ImageFont.load_default(size=size)
    font = ImageFont.truetype(path, size)
    if values:
        font.set_variation_by_axes(list(values))
    return font


# --- a face at a size ----------------------------------------------------------------------------


class Face:
    """The platform's UI face at a CSS weight and size: glyph advances, kerning and tracking in
    pixels, and its em box's top above the baseline (where ``textBaseline = "top"`` puts words)."""

    def __init__(self, weight: float, size: float) -> None:
        self.path, self.name = face_source(float(weight))
        self.size, self.weight = float(size), float(weight)
        self.font = _opentype(self.path) if self.path else None
        font = self.font
        self.values = tuple(font.location({"wght": self.weight, "opsz": self.size})) if font and font.axes else ()
        self.coords = tuple(font.normalised(list(self.values))) if self.values else ()
        if font:
            self.upm = font.upm
            ascent, descent = font.ascent, font.descent
            self.track = font.track(self.size) * self.size / self.upm
        else:
            self.upm = 1000
            ascent, descent = _pillow_font(None, 1000.0, ()).getmetrics()
            self.track = 0.0
        self.em_top = self.size * ascent / (ascent + descent)  # the em box's top above the baseline
        self.mac = self.path == str(MAC_FACE)
        self._advances: dict[str, float] = {}
        self._kerns: dict[tuple[str, str], float] = {}

    def advance(self, char: str) -> float:
        """A character's advance in font units: FreeType's at the font's own units per em."""
        found = self._advances.get(char)
        if found is None:
            found = self._advances[char] = float(_pillow_font(self.path, float(self.upm), self.values).getlength(char))
        return found

    def kern(self, left: str, right: str) -> float:
        if self.font is None:
            return 0.0
        found = self._kerns.get((left, right))
        if found is None:
            found = self._kerns[(left, right)] = self.font.kern(self.font.glyph(left), self.font.glyph(right), self.coords)
        return found

    def layout(self, line: str) -> tuple[list[float], float]:
        """Each glyph's pen position from the line's start, and the line's width, as Chromium's
        ``measureText`` gives it, in pixels."""
        scale = self.size / self.upm
        positions, pen = [], 0.0
        for index, char in enumerate(line):
            positions.append(pen)
            pen += self.advance(char) * scale + self.track
            if index + 1 < len(line):
                pen += self.kern(char, line[index + 1]) * scale
        return positions, pen

    def width(self, line: str) -> float:
        return self.layout(line)[1]


@lru_cache(maxsize=32)
def face(weight: float, size: float) -> Face:
    """The face at ``weight`` and ``size``, made once per process."""
    return Face(weight, size)


def _dilation(face_: Face, size: float) -> float:
    """macOS's font smoothing, as Chromium's canvas text shows it there (fitted): each side of an
    outline grown by ``0.00605 x size`` pixels, at most 0.3, none from 72 px up. Elsewhere none."""
    return 0.0 if not face_.mac or size >= 72 else min(0.00605 * size, 0.3)


def coverage(lines: list[str], face_: Face, size: tuple[int, int], origin: tuple[float, float],
             line_step: float, scale: float = 1.0, align: str = "left") -> np.ndarray:
    """The words' coverage (0 to 1) on a ``size`` (width, height) picture: line ``i``'s em box
    top at ``origin + (0, i x line_step)``, everything in the face's pixels times ``scale`` (a
    canvas transform); ``align`` "center" centres each line on ``origin``'s x. The baseline is on
    a whole pixel, as Skia puts axis-aligned text."""
    from PIL import Image, ImageDraw

    ss = SUPERSAMPLE
    raster = _pillow_font(face_.path, face_.size * scale * ss, face_.values)
    picture = Image.new("L", (size[0] * ss, size[1] * ss), 0)
    draw = ImageDraw.Draw(picture)
    grow = int(round(_dilation(face_, face_.size * scale) * ss))
    shift = MAC_BASELINE_SHIFT if face_.mac else 0.0
    for index, line in enumerate(lines):
        positions, width = face_.layout(line)
        left = origin[0] - (width * scale / 2 if align == "center" else 0.0)
        baseline = round(origin[1] + index * line_step + face_.em_top * scale) + shift
        for char, at in zip(line, positions):
            if char.isspace():
                continue
            draw.text(((left + at * scale) * ss, baseline * ss), char, font=raster, fill=255, anchor="ls",
                      stroke_width=grow, stroke_fill=255)
    return np.asarray(picture.reduce(ss), np.float64) / 255.0


def text_canvas(text: str, font_px: float, color: str) -> np.ndarray:
    """A text mark's picture as the viewer makes it (``textCanvas``): RGBA bytes, (height, width,
    4), the colour where there is ink (as a canvas hands its pixels to WebGL: not premultiplied,
    nothing where there is none)."""
    lines = str(text).split("\n")
    face_ = face(500, font_px * TEXT_SCALE)
    width = max(1.0, *(face_.width(line) for line in lines))
    size = (int(math.ceil(width)) + 2, int(math.ceil(len(lines) * font_px * LINE_HEIGHT * TEXT_SCALE)) + 2)
    if size[0] * size[1] * SUPERSAMPLE * SUPERSAMPLE > MAX_TEXT_RASTER:
        raise ValueError(f"a text mark's canvas is {size[0]}x{size[1]} at {SUPERSAMPLE}x; over {MAX_TEXT_RASTER} px")
    alpha = coverage(lines, face_, size, (1.0, 1.0), font_px * LINE_HEIGHT * TEXT_SCALE)
    rgb = np.array([int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.uint8)
    out = np.zeros((size[1], size[0], 4), np.uint8)
    a = np.rint(alpha * 255).astype(np.uint8)
    out[..., 3] = a
    out[a > 0, :3] = rgb
    return out


def measure(text: str, font_px: float, weight: float = 500) -> float:
    """``measureText(text).width`` for the viewer's face at ``font_px``: a text mark's quad width."""
    return max(face(weight, font_px).width(line) for line in str(text).split("\n"))
