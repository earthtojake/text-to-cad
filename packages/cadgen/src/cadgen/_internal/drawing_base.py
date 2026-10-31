"""The vocabulary every part of a drawing shares: sheet sizes, view directions,
layers, standard scales, and how text is measured and its symbols drawn.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache


#: ISO 216 sheet sizes, landscape, in millimetres.
SHEET_SIZES = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}

#: Standard view names -> (view direction: where the viewer STANDS relative to the
#: part, up vector). Third-angle projection places each view on the side it looks
#: from; the sheet does not enforce placement, the author picks ``at=``.
VIEW_DIRECTIONS = {
    "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    # Looking up from below, the sheet's up is the model's -Y: the bottom view is the
    # top view mirrored about the horizontal, which is what third angle draws. With
    # up=+Y it comes out rotated 180 degrees (+X to the left), so it would not line up
    # with the front view above it.
    "bottom": ((0.0, 0.0, -1.0), (0.0, -1.0, 0.0)),
    "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "iso": ((1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
}

#: Layers a sheet writes, with ACI colour and linetype. ``ink="mono"`` collapses
#: the colours to the default ink; the linetypes are the drawing's meaning and stay.
#: Every linetype here must be one ``ezdxf.new(setup=True)` defines, or ezdxf draws
#: the layer continuous and its audit reports the substitution: there is no HIDDEN
#: in that table, DASHED is the ISO 128 dashed line it does define.
_LAYERS = {
    "SHEET": (7, "CONTINUOUS", 0.35),
    "TITLE": (7, "CONTINUOUS", 0.25),
    "VISIBLE": (7, "CONTINUOUS", 0.5),
    "HIDDEN": (8, "DASHED", 0.25),
    "CENTER": (4, "CENTER", 0.18),
    "DIM": (1, "CONTINUOUS", 0.18),
    "NOTES": (3, "CONTINUOUS", 0.25),
    # A section's cut faces: 45-degree lines, thin, as ISO 128-50 hatches them.
    "HATCH": (8, "CONTINUOUS", 0.18),
}
#: Letters a section may be named by: ISO 128-40 leaves out I, O and Q, which read
#: as 1, 0 and O on a print.
_SECTION_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"
#: ANSI31 at this scale is 45-degree lines 3.2 mm apart: legible on A4, not grey on A0.
_HATCH_SCALE = 1.0
#: The material families a part may be stated as, and the ANSI pattern a section
#: hatches each with, at an angle (degrees) where two families share a pattern.
#: The sheet's material key says which pattern is which material.
HATCHES = {
    "steel": ("ANSI32", 0.0), "iron": ("ANSI31", 0.0), "aluminium": ("ANSI38", 0.0),
    "copper_alloy": ("ANSI33", 0.0), "plastic": ("ANSI34", 0.0), "elastomer": ("ANSI34", 90.0),
    "composite": ("ANSI37", 0.0), "fabric": ("ANSI37", 90.0), "glass": ("ANSI36", 0.0), "general": ("ANSI31", 0.0),
}
FAMILIES = tuple(HATCHES)

#: Projection conventions the title block may name. The two differ only in WHERE a
#: view is placed: third angle puts the view from above above the front view and the
#: view from the right to its right; first angle puts each on the opposite side. The
#: pictures are the same, so only :meth:`Sheet.three_views` reads this.
PROJECTIONS = ("THIRD ANGLE", "FIRST ANGLE")

_MARGIN = 10.0
_TITLE_W, _TITLE_H = 180.0, 40.0
#: The band a sheet's stage, profile or company adds across the title block's top.
_BAND_H = 10.0
#: Text height the notes block is drawn at, and the left inset of its first glyph.
#: The guard that refuses an over-wide note measures at these, because a guard
#: that measures a different string at a different height than the draw either
#: refuses a note that fits or passes one that does not.
_NOTE_HEIGHT = 2.5
_NOTE_INSET = 3.0
#: One row of dimensions: the line's distance from the last, with room for its text.
_DIM_ROW = 12.0
#: A view's label: its gap below everything under the view, and its height.
_LABEL_GAP = 6.0
_LABEL_HEIGHT = 3.5
#: What a view's label takes below the view, with air under it.
_LABEL_ROOM = _LABEL_GAP + _LABEL_HEIGHT + 2.0
#: A callout's leader: how far past the view's annotation its knee stands, the
#: level landing from the knee, and the gap between the landing and the text,
#: which is also the air the text keeps beyond it. The layout plans with these
#: and the drawing draws with them.
_CALLOUT_CLEAR = 10.0
_CALLOUT_LANDING = 6.0
_CALLOUT_GAP = 2.0
#: Callouts landing on one side stand this many text heights apart.
_CALLOUT_STACK = 2.2
#: The text height a sheet draws at unless told otherwise.
_DEFAULT_TEXT = 3.5
#: The smallest text a print stays legible at. Below it, text is cut, not shrunk.
_MIN_TEXT_MM = 1.6
#: Drawing scales a shop expects to read, largest first. An over-size part is
#: refused with the first of these that fits rather than an arbitrary ratio.
_STANDARD_SCALES = (50.0, 20.0, 10.0, 5.0, 2.0, 1.0, 1 / 2, 1 / 2.5, 1 / 5, 1 / 10, 1 / 20, 1 / 50, 1 / 100,
                    1 / 200, 1 / 500, 1 / 1000)
#: The only unit a sheet prints. Every value on it is measured off the model, whose
#: unit is the millimetre; a title block reading IN over millimetre values is a
#: drawing that is wrong by 25.4 everywhere and looks right.
UNITS = ("mm",)


def _fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


#: The most decimal places a stated tolerance or limit prints to. A value is printed
#: as given, never rounded: rounded, a tolerance of 0.005 printed 0.01, a
#: requirement nobody stated.
_MOST_PLACES = 4


def _places(*values: float) -> int:
    """The decimal places that print every one of ``values`` exactly."""
    for places in range(_MOST_PLACES + 1):
        if all(abs(round(v, places) - v) < 1e-9 for v in values):
            return places
    raise ValueError(f"{', '.join(repr(v) for v in values)}: a stated tolerance prints exactly as given, to at "
                     f"most {_MOST_PLACES} decimal places")


def _exact(value: float) -> str:
    """A stated value as given, to its own decimal places."""
    return f"{value:.{_places(value)}f}"


def _p3(p) -> tuple[float, float, float]:
    try:
        values = tuple(float(v) for v in p)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"expected a model point like (x, y, z), got {p!r}") from exc
    if len(values) == 2:
        values = (values[0], values[1], 0.0)
    if len(values) != 3:
        raise ValueError(f"expected a 2D or 3D point, got {p!r}")
    return values  # type: ignore[return-value]


def _dirs(view) -> tuple:
    """Where a view's viewer stands, and its up: an auxiliary view's own, or its name's."""
    return view._direction or VIEW_DIRECTIONS[view.name]


def _view_axes(name: str) -> tuple[int, int]:
    """The model axes a principal view shows across and up the sheet."""
    look, up = VIEW_DIRECTIONS[name]
    vertical = next(k for k in range(3) if up[k])
    return next(k for k in range(3) if k != vertical and not look[k]), vertical


def _look(view) -> tuple[float, float, float]:
    """The unit vector from the part toward the view's viewer. The isometric's
    direction is not unit length, and a dot product with it is only a cosine
    once it is."""
    x, y, z = _dirs(view)[0]
    length = math.sqrt(x * x + y * y + z * z)
    return (x / length, y / length, z / length)


# --- text and symbols -----------------------------------------------------------------

def _dimstyle(doc, text_height: float):
    style = doc.dimstyles.get("Standard")
    style.dxf.dimtxt = text_height
    style.dxf.dimasz = text_height * 0.85
    style.dxf.dimexo = 1.5
    style.dxf.dimexe = 2.0
    style.dxf.dimgap = 1.0
    style.dxf.dimtad = 1
    style.dxf.dimdec = 2
    style.dxf.dimzin = 8
    style.dxf.dimdsep = ord(".")
    style.dxf.dimtdec = 2
    style.dxf.dimblk = "_CLOSEDFILLED"
    return "Standard"


def _spans(a, b) -> str:
    """Whether a projected point pair reads as a horizontal or a vertical dimension."""
    return "h" if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else "v"


def _scale_label(scale: float, digits: str = "g") -> str:
    """"1:2", "2:1", "1:1". ``digits`` rounds a scale nobody chose, such as the
    one an isometric fitted itself to, to something a reader can take in."""
    if abs(scale - 1) < 1e-9:
        return "1:1"
    return f"1:{1 / scale:{digits}}" if scale < 1 else f"{scale:{digits}}:1"


#: Fallback width per character, as a multiple of cap height, for when the font
#: the renderer uses cannot be measured. Set at the wide end of what was
#: measured (0.70 for "+0.10", 0.89 for "ELECTRONICS ENCLOSURE BASE") so the
#: fallback overruns nothing.
_CHAR_WIDTH = 0.9
#: MTEXT's own control codes: a backslash, a letter, and everything to the ";".
_MTEXT_CODE = re.compile(r"\\([A-Za-z])([^;]*);")


@lru_cache(maxsize=8)
def _font(height: float):
    """The renderer's own font at a cap height, or None if it cannot be had.

    A constant width per character is wrong for every proportional font: the
    same ratio that fits "ELECTRONICS ENCLOSURE BASE" runs "+0.10" 25% over.
    ezdxf measures the glyphs it is about to draw, so ask it.
    """
    try:
        from ezdxf.fonts import fonts

        return fonts.make_font("txt.shx", height)
    except Exception:  # noqa: BLE001 - no font manager, no cache; fall back to a ratio
        return None


def _text_width(value: str, height: float) -> float:
    """How wide `value` prints at this cap height, in millimetres."""
    if not value:
        return 0.0
    # %%c, %%d and %%p each draw one glyph; measured as written they read three wide.
    value = value.replace("%%c", "Ø").replace("%%d", "°").replace("%%p", "±")
    font = _font(round(float(height), 4))
    if font is None:
        return len(value) * height * _CHAR_WIDTH
    try:
        return float(font.text_width(value))
    except Exception:  # noqa: BLE001 - an unmappable glyph is not worth a failed drawing
        return len(value) * height * _CHAR_WIDTH


def _mtext_extent(raw: str, height: float) -> tuple[float, float]:
    """The width and height of rendered MTEXT, from the glyphs it actually draws.

    A dimension's value lives as MTEXT markup, and the markup is not the text:
    a toleranced ``30`` is ``\\A0;30{\\H0.70x;±0.10}``, 15 characters of which 7
    draw nothing and 5 draw at 0.7 of the height. Counted raw at full height
    that estimated 37.8 mm of ink where 14 mm exists, and every chain-dimensioned
    toleranced row -- the commonest idiom in drafting -- reported an overlap.
    """
    lines: list[float] = []
    width = 0.0
    tallest = height
    factor = 1.0
    run: list[str] = []

    def flush() -> None:
        nonlocal width
        if run:
            width += _text_width("".join(run), height * factor)
            run.clear()

    index = 0
    while index < len(raw):
        char = raw[index]
        if char in "{}":
            index += 1
        elif char == "\\" and raw[index + 1:index + 2] in ("\\", "{", "}"):
            run.append(raw[index + 1])
            index += 2
        elif char == "\\" and raw[index + 1:index + 2] in ("P", "p"):
            flush()
            lines.append(width)
            width, tallest = 0.0, tallest + height * factor
            index += 2
        elif char == "\\" and (match := _MTEXT_CODE.match(raw, index)):
            code, body = match.group(1), match.group(2)
            flush()
            if code in "Hh":
                # \H0.70x; is relative to the current height, \H2.5; absolute.
                try:
                    value = float(body.rstrip("xX"))
                except ValueError:
                    value = 1.0
                factor = value if body[-1:].lower() == "x" else (value / height if height else 1.0)
            elif code in "Ss":
                # A stacked tolerance prints its halves one above the other, so
                # it is as wide as the wider half, not as wide as both.
                upper, _, lower = body.partition("^")
                # Charged at the height in force, not smaller again: the halves
                # draw at some fraction of it that varies by renderer, and a box
                # that errs wide misses no overlap.
                stacked = height * factor
                width += max(_text_width(upper.strip("^ "), stacked),
                             _text_width(lower.strip("^ "), stacked))
                tallest = max(tallest, 2 * stacked)
            index = match.end()
        elif raw.startswith("%%", index) and raw[index + 2:index + 3]:
            run.append("Ø")  # %%c, %%d and %%p each draw exactly one glyph
            index += 3
        else:
            run.append(char)
            index += 1
    flush()
    lines.append(width)
    return max(lines), tallest


#: The drawing symbols a callout prints, drawn as line work rather than set as
#: glyphs. Glyphs for them are a property of whatever font the machine resolves:
#: ⌴ and ⌵ are missing from Arial and DejaVu alike (an empty box where the
#: counterbore should be), and ezdxf fills the crossing strokes of Ø solid in
#: every font that has it. Drawn, they print the same on every machine.
_SYMBOLS = {"%%c": "diameter", "Ø": "diameter", "\u2300": "diameter", "\u21a7": "depth",
            "\u2334": "cbore", "\u2335": "csk"}
#: Each symbol's advance, as a multiple of the cap height.
_SYMBOL_ADVANCE = {"diameter": 1.0, "depth": 0.8, "cbore": 1.0, "csk": 1.0}


def _runs(value: str) -> list[tuple[str, str]]:
    """``value`` split into ("text", run) and ("symbol", kind) pieces."""
    out: list[tuple[str, str]] = []
    run: list[str] = []
    index = 0
    while index < len(value):
        token = next((t for t in _SYMBOLS if value.startswith(t, index)), None)
        if token is None:
            run.append(value[index])
            index += 1
            continue
        if run:
            out.append(("text", "".join(run)))
            run = []
        out.append(("symbol", _SYMBOLS[token]))
        index += len(token)
    if run:
        out.append(("text", "".join(run)))
    return out


def _ink_width(value: str, height: float) -> float:
    """How wide ``value`` prints with its symbols drawn: what a callout occupies."""
    return sum(_text_width(piece, height) if kind == "text" else _SYMBOL_ADVANCE[piece] * height
               for kind, piece in _runs(value))


def _symbol(kind: str, x: float, mid: float, h: float) -> list[tuple]:
    """One symbol as line work, its advance box starting at ``x`` and centred on
    ``mid``, in the proportions ASME Y14.5 and ISO 129 draw them: ``("circle",
    centre, radius)`` and ``("line", points)`` pieces."""
    y0 = mid - h / 2
    if kind == "diameter":
        centre, r = (x + 0.5 * h, mid), 0.38 * h
        dx, dy = 0.55 * h * math.cos(math.radians(60)), 0.55 * h * math.sin(math.radians(60))
        return [("circle", centre, r), ("line", [(centre[0] - dx, mid - dy), (centre[0] + dx, mid + dy)])]
    if kind == "depth":
        stem = x + 0.4 * h
        return [("line", [(stem, y0 + h), (stem, y0)]),
                ("line", [(stem - 0.22 * h, y0 + 0.4 * h), (stem, y0), (stem + 0.22 * h, y0 + 0.4 * h)]),
                ("line", [(x + 0.08 * h, y0), (x + 0.72 * h, y0)])]
    if kind == "cbore":
        return [("line", [(x + 0.12 * h, y0 + 0.75 * h), (x + 0.12 * h, y0), (x + 0.88 * h, y0),
                          (x + 0.88 * h, y0 + 0.75 * h)])]
    return [("line", [(x + 0.1 * h, y0 + 0.8 * h), (x + 0.5 * h, y0), (x + 0.9 * h, y0 + 0.8 * h)])]


def _draw_symbol(layout, kind: str, x: float, mid: float, h: float, layer: str, place=None) -> None:
    """Write :func:`_symbol`'s pieces into ``layout``, through ``place`` (a map from
    the symbol's own frame to the layout's) when the text it sits in is rotated."""
    place = place or (lambda p: p)
    # Stroked as heavy as the glyphs beside it, not at the layer's hairline.
    attribs = {"layer": layer, "lineweight": max(13, min(50, int(round(h * 10))))}
    for piece in _symbol(kind, x, mid, h):
        if piece[0] == "circle":
            layout.add_circle(place(piece[1]), piece[2], dxfattribs=attribs)
        else:
            layout.add_lwpolyline([place(p) for p in piece[1]], dxfattribs=attribs)


def _draw_dimension_symbols(doc, dimension, layer: str = "DIM") -> None:
    """A dimension's value prefixed with ⌀ (``text="%%c<>"``) gets the symbol drawn
    in its block, beside the number, instead of set as a glyph."""
    try:
        block = doc.blocks.get(dimension.dxf.geometry)
    except Exception:  # noqa: BLE001 - nothing rendered, nothing to draw
        return
    for entity in list(block):
        if entity.dxftype() != "MTEXT":
            continue
        raw = str(entity.text or "")
        head = re.match(r"((?:\\A\d;)?)(%%c|Ø)", raw)
        if not head:
            continue
        rest = raw[: head.start(2)] + raw[head.end(2):]
        h = float(entity.dxf.char_height)
        advance = _SYMBOL_ADVANCE["diameter"] * h
        width, _tall = _mtext_extent(rest, h)
        angle = math.radians(float(entity.dxf.rotation or 0.0))
        along, across = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
        insert = entity.dxf.insert

        def place(p, insert=insert, along=along, across=across):
            return (insert.x + p[0] * along[0] + p[1] * across[0], insert.y + p[0] * along[1] + p[1] * across[1])

        # The value was centred on the insert; symbol and number now share the space.
        _draw_symbol(block, "diameter", -(width + advance) / 2, 0.0, h, layer, place)
        entity.text = rest
        entity.dxf.insert = place((advance / 2, 0.0))


#: The air between a basic dimension's value and its box, in text heights.
_BASIC_AIR = 0.3


def _box_text(layout, box: tuple[float, float, float, float], *, angle: float = 0.0,
              air: float | None = None) -> None:
    """Frame a value, as a basic dimension's is framed: ``box`` is its text's
    (x0, y0, x1, y1) before turning by ``angle`` degrees about its middle."""
    x0, y0, x1, y1 = box
    pad = _BASIC_AIR * (y1 - y0) if air is None else air
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (x1 - x0) / 2 + pad, (y1 - y0) / 2 + pad
    turn = math.radians(angle)
    corners = [(cx + dx * math.cos(turn) - dy * math.sin(turn), cy + dx * math.sin(turn) + dy * math.cos(turn))
               for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
    layout.add_lwpolyline(corners, close=True, dxfattribs={"layer": "DIM"})


#: A flag note's triangle, its side in text heights, and its number's height in sides.
_FLAG_SIDE = 2.0
_FLAG_NUMBER = 0.38


def _draw_flag(layout, number: str, x: float, mid: float, side: float,
               layer: str) -> tuple[float, float, float, float]:
    """A flag note's symbol: an upright equilateral triangle of ``side``, its base
    from ``x``, its middle at height ``mid``, the note's number in it. Returns its
    box (x0, y0, x1, y1)."""
    from ezdxf.enums import TextEntityAlignment

    tall = side * math.sqrt(3) / 2
    base = mid - tall / 2
    layout.add_lwpolyline([(x, base), (x + side, base), (x + side / 2, base + tall)], close=True,
                          dxfattribs={"layer": layer})
    label = layout.add_text(number, dxfattribs={"height": side * _FLAG_NUMBER, "layer": layer})
    label.set_placement((x + side / 2, base + tall / 3), align=TextEntityAlignment.MIDDLE_CENTER)
    return x, base, x + side, base + tall


def _box_dimension_value(doc, dimension) -> None:
    """Frame a basic dimension's value in its own block. ezdxf marks a basic value
    with a negative DIMGAP but leaves the frame undrawn."""
    block = doc.blocks.get(dimension.dxf.geometry)
    for value in [e for e in block if e.dxftype() == "MTEXT"]:
        width, tall = _mtext_extent(value.text, value.dxf.char_height)
        x, y = value.dxf.insert.x, value.dxf.insert.y
        _box_text(block, (x - width / 2, y - tall / 2, x + width / 2, y + tall / 2),
                  angle=float(value.dxf.get("rotation", 0.0) or 0.0))


def _text_box(value: str, x: float, y: float, height: float, align) -> tuple[float, float, float, float]:
    """The rectangle a TEXT entity occupies, from its anchor and alignment."""
    width = _ink_width(value, height)
    name = getattr(align, "name", str(align)).upper()
    if "CENTER" in name and "LEFT" not in name and "RIGHT" not in name:
        x0 = x - width / 2
    elif "RIGHT" in name:
        x0 = x - width
    else:
        x0 = x
    if "TOP" in name:
        y0 = y - height
    elif "MIDDLE" in name:
        y0 = y - height / 2
    else:
        y0 = y
    return (x0, y0, x0 + width, y0 + height)


#: Where each standard view's opposite stands, for "call it out there instead".
_OPPOSITE = {"top": "bottom", "bottom": "top", "front": "back", "back": "front",
             "right": "left", "left": "right", "iso": "iso"}
#: Model millimetres within which a point a callout was given and a feature's
#: projected centre are the same place.
_SAME_PLACE = 0.05
#: How far a centre line runs past the feature it marks, in sheet millimetres.
_CENTRE_OVERSHOOT = 3.0
#: What a cutting plane's end takes past the view it crosses: the line's overshoot
#: and the letter beside it.
_PLANE_ROOM = 12.0
#: The most a detail's circle is drawn across when its scale is left to the sheet.
_DETAIL_SIZE = 60.0
_SIDES = ("top", "bottom", "left", "right")


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _looks_down(axis, look) -> bool:
    """Whether a view looking along unit ``look`` sees unit ``axis`` end-on."""
    return abs(_dot(axis, look)) > 1 - 1e-6


def _near(p, q, tol: float = _SAME_PLACE) -> bool:
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def _where(p) -> str:
    return "(" + ", ".join(_fmt(v) for v in p) + ")"


def _shown(text: str) -> str:
    """Callout text as a message prints it: the diameter sign, not its DXF escape."""
    return text.replace("%%c", "⌀")
