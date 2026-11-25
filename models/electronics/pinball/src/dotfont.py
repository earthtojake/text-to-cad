"""A 5 x 7 dot-matrix font: the machine's one typeface, the same grid its display draws.

`dots(text, pitch)` places a dot per lit cell: (x, y) centres, the text's left edge at x = 0 and its
baseline (the bottom row) at y = 0, y up. The art draws each as a gold pad or a silkscreen dot, the
backbox's title as lit windows, the display as LEDs, the firmware as pixels: one glyph table.
"""
from __future__ import annotations

GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11100", "10010", "10001", "10001", "10001", "10010", "11100"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "10001", "11001", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    " ": ["00000"] * 7,
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "/": ["00000", "00001", "00010", "00100", "01000", "10000", "00000"],
    "x": ["00000", "00000", "10001", "01010", "00100", "01010", "10001"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
    "*": ["00000", "10101", "01110", "11111", "01110", "10101", "00000"],
    "=": ["00000", "00000", "11111", "00000", "11111", "00000", "00000"],
    ",": ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
}


def advance(ch: str) -> int:
    """Columns a glyph takes, its gap included (5 + 1; a space is 3)."""
    return 3 if ch == " " else 6


def width(text: str, pitch: float) -> float:
    cols = sum(advance(c) for c in text) - 1
    return cols * pitch


def dots(text: str, pitch: float) -> list[tuple[float, float]]:
    """The lit cells' centres: left edge x = 0, bottom row y = 0, y up."""
    out = []
    col = 0
    for ch in text:
        glyph = GLYPHS.get(ch) or GLYPHS[ch.upper()]
        for r, row in enumerate(glyph):
            for c, bit in enumerate(row):
                if bit == "1":
                    out.append(((col + c) * pitch, (6 - r) * pitch))
        col += advance(ch)
    return out


def placed(text: str, pitch: float, at: tuple[float, float], anchor: str = "center", rotate: float = 0.0):
    """`dots` moved so the text's anchor ("center", "left", "right") sits at `at` (its middle row on at's y)."""
    import math
    w = width(text, pitch)
    dx = {"center": -w / 2, "left": 0.0, "right": -w}[anchor]
    dy = -3 * pitch
    c, s = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))
    out = []
    for x, y in dots(text, pitch):
        x, y = x + dx, y + dy
        out.append((at[0] + x * c - y * s, at[1] + x * s + y * c))
    return out


def strokes(text: str, pitch: float):
    """The text drawn as copper traces: each glyph's lit cells joined to their lit neighbours (across and
    down; a diagonal only where no square path joins the two), as segments [((x0, y0), (x1, y1))], and the
    trace ends (cells with one neighbour, or none) where a via sits. Frame as `dots`."""
    segs, ends = [], []
    col = 0
    for ch in text:
        glyph = GLYPHS.get(ch) or GLYPHS[ch.upper()]
        lit = {(r, c) for r, row in enumerate(glyph) for c, bit in enumerate(row) if bit == "1"}

        def at(r, c):
            return ((col + c) * pitch, (6 - r) * pitch)
        degree = {cell: 0 for cell in lit}
        for (r, c) in lit:
            for dr, dc in ((0, 1), (1, 0)):
                if (r + dr, c + dc) in lit:
                    segs.append((at(r, c), at(r + dr, c + dc)))
                    degree[(r, c)] += 1
                    degree[(r + dr, c + dc)] += 1
            for dc in (1, -1):
                other = (r + 1, c + dc)
                if other in lit and (r, c + dc) not in lit and (r + 1, c) not in lit:
                    segs.append((at(r, c), at(*other)))
                    degree[(r, c)] += 1
                    degree[other] += 1
        ends += [at(r, c) for (r, c), d in degree.items() if d <= 1]
        col += advance(ch)
    return segs, ends


def placed_strokes(text: str, pitch: float, at, anchor: str = "center"):
    w = width(text, pitch)
    dx = {"center": -w / 2, "left": 0.0, "right": -w}[anchor] + at[0]
    dy = -3 * pitch + at[1]
    segs, ends = strokes(text, pitch)
    return ([((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy)) for a, b in segs],
            [(x + dx, y + dy) for x, y in ends])
