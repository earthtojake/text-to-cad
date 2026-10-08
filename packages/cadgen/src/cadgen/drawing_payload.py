"""A DXF flattened into a 2D render payload by ezdxf's drawing add-on.

One function does the work: ``ezdxf``'s frontend walks the modelspace and
hands a backend the primitives every entity reduces to — dimensions exploded
to their lines, arrow heads and text, hatches to fills or pattern lines, block
references to the geometry of their contents, MTEXT to its laid-out lines and
words. Nothing here knows about LINE or ARC or HATCH; the add-on already
resolved all of that, which is the whole reason this module is 500 lines
instead of 4000.

Coordinates are DXF modelspace coordinates, **y up**, rounded to
``_COORDINATE_DECIMALS`` places. Rounding is not cosmetic: a flat pattern's
payload shrinks ~3x, and the rounded numbers are also what ``bounds`` is
computed from, so a consumer that fits the view to ``bounds`` fits it to the
geometry it will actually draw.

Text
----
Text stays text. The add-on would outline every glyph into filled paths — about
23 KB of payload, and most of the render's time, per line of text, so a sheet of
notes became a hundred megabytes nobody could open. Instead the pipeline's one
text hook (``draw_text``) is given the string where the add-on has placed it: a
``text`` primitive carries the string, the font it is set in, its cap height,
the advance width ezdxf measured for it in that font, and the affine transform
from its own space (baseline-left at the origin, y up) to the drawing. ezdxf has
already applied alignment, rotation, width factor, oblique, mirroring and block
transforms to that transform, and broken MTEXT into lines and words; a client
sets the string at that cap height, stretches it to that width (so a font that
differs from ezdxf's keeps the layout ezdxf computed), and paints it. Text inside
a clipped block reference is still outlined, because only paths can be clipped.

The default pen
---------------
A DXF entity that resolves to ACI 7 has no colour of its own: 7 means
"whatever contrasts with the background", which is why AutoCAD draws it white
on black and black on white. ezdxf answers that question by guessing a
background, and a payload that bakes in the guess is wrong in one of the two
themes. So the frontend is handed an explicit layout foreground — a SENTINEL
colour — and every primitive that comes back wearing it is emitted with
``color: null``, meaning "paint this with the theme's foreground". Every other
ACI and every true colour is a literal ``#rrggbb``.

The sentinel is a colour no ACI in the palette resolves to. A true colour that
happens to equal it exactly would be read as the default pen; that is the one
degenerate case, and it costs a near-black line the theme's foreground instead
of its own near-black.

Storage
-------
The payload is derived data, cached in the store's ``drawing`` index — keyed by
the document's bytes plus this extraction's scheme, exactly as every other
input-addressed derivation is (``STORE.md`` §2). ``drawing_payload_bytes`` is
the door: a second call for unchanged bytes never re-enters ezdxf, and never
even imports it. Its two halves — ``cached_drawing_payload`` and
``render_drawing_payload`` under one ``drawing_payload_key`` — are there for a
caller that renders off its request (the CAD Viewer's route).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import random
import threading
from pathlib import Path

__all__ = [
    "DRAWING_PAYLOAD_SCHEMA_VERSION",
    "DrawingReadError",
    "build_drawing_payload",
    "cached_drawing_payload",
    "drawing_extraction_scheme",
    "drawing_payload_bytes",
    "drawing_payload_key",
    "encode_drawing_payload",
    "read_drawing_document",
    "render_drawing_payload",
]

# Bumped when the payload's SHAPE changes. It rides in the payload (a client
# checks it before drawing) and in the cache key (an old shape is not served
# from the store after an upgrade). 2: text is a `text` primitive and the
# payload lists its `fonts`, where 1 outlined every glyph into `filled-paths`.
# 3: a primitive may carry its own `opacity`, and a stroke its own screen
# `width` (CSS pixels), which a STEP section's drawing uses
# (cadgen.section_drawing); a DXF's never does.
DRAWING_PAYLOAD_SCHEMA_VERSION = 3

# The layout foreground handed to ezdxf, and therefore the exact colour every
# default-pen primitive comes back wearing. Not in the ACI palette; see the
# module docstring.
_DEFAULT_PEN_SENTINEL = "#010203"
# The background only decides which foreground ezdxf would have guessed, and we
# do not let it guess. It is still pinned so nothing downstream varies with it.
_SENTINEL_BACKGROUND = "#ffffff"

_COORDINATE_DECIMALS = 4
# A text transform's linear part (rotation, width factor, oblique, scale) is
# kept finer than a coordinate: it multiplies the whole length of a line of text.
_LINEAR_DECIMALS = 6

# ezdxf's own primitive names, unchanged: "point", "lines", "path",
# "filled-paths", "filled-polygon". Renaming them would create a second
# vocabulary for one set of shapes. "text" is this module's: ezdxf has no
# primitive for a string it has not outlined.
_TEXT = "text"

_extraction_scheme: str | None = None

# ezdxf offsets a pattern hatch's base lines by `random.random()` "to avoid
# intersections" with the boundary's corners, from the PROCESS-WIDE random
# module. Left alone, the same drawing renders differently every time and
# nothing downstream of this module can be compared, diffed or byte-pinned. The
# stream is seeded to a constant for the render and restored afterwards, under
# a lock so two renders cannot interleave their seeding. The constant is
# arbitrary; only its fixity matters.
_JIGGLE_SEED = 0x64786673
_render_guard = threading.Lock()


class DrawingReadError(ValueError):
    """A ``.dxf`` that cannot be turned into a payload, with the reason.

    A ``ValueError``, so the Viewer's GET funnel answers 400 with the message —
    which is why every message here names what is wrong AND what to do.
    """


# --- reading ---------------------------------------------------------------


def read_drawing_document(path):
    """The parsed ``ezdxf`` document, recovering a damaged file once.

    ``ezdxf.readfile`` is strict. When it rejects the structure,
    ``ezdxf.recover.readfile`` re-reads the same bytes tolerantly (it repairs
    the classes of damage other CAD software writes); anything it cannot make
    sense of raises with the reason rather than an empty drawing.
    """
    import ezdxf
    import ezdxf.recover

    text = str(path)
    try:
        return ezdxf.readfile(text)
    except FileNotFoundError:
        raise DrawingReadError(f"{Path(text).name} does not exist; check the path") from None
    except (PermissionError, IsADirectoryError) as error:
        raise DrawingReadError(
            f"{Path(text).name} could not be opened ({error}); "
            "check that it is a file this user may read"
        ) from None
    except (ezdxf.DXFError, OSError, ValueError, UnicodeDecodeError):
        # Everything else is "these bytes did not parse", however ezdxf spells
        # it — a bad structure is a DXFStructureError, but a file that is not a
        # DXF at all comes back as a bare OSError. Both get the second attempt.
        pass
    try:
        document, _auditor = ezdxf.recover.readfile(text)
    except (ezdxf.DXFError, OSError, ValueError) as error:
        raise DrawingReadError(
            f"{Path(text).name} is not a readable DXF ({error}); "
            "re-export it from the program that made it, or run "
            "`ezdxf audit` on it to see what is damaged"
        ) from None
    return document


# --- rendering -------------------------------------------------------------


class _DefaultPenLayers(dict):
    """``RenderContext.layers`` with ONE change: an undefined layer is ACI 7.

    An entity may name a layer the LAYER table never defined. ezdxf falls back
    to a module-level default whose colour is a hard-coded white — invisible on
    a light theme, and not what a CAD program does with such a file (it creates
    the layer with the default pen). The fallback here resolves to the default
    pen instead, so the entity is drawn with the theme's foreground.
    """

    __slots__ = ("_fallback",)

    def __init__(self, layers, fallback):
        super().__init__(layers)
        self._fallback = fallback

    def get(self, key, default=None):
        found = dict.get(self, key)
        return self._fallback if found is None else found


_text_pipeline_class = None


def _text_pipeline(backend):
    """ezdxf's 2D render pipeline, with ONE change: text reaches the backend as text.

    ``RenderPipeline2d.draw_text`` is the single place every TEXT, ATTRIB, MTEXT
    line, MTEXT word and dimension label passes through, already placed: the
    string (one line, never a newline), the transform from its own space to the
    drawing, and its cap height. ezdxf outlines it there; this hands the backend
    a ``text`` record instead (the module docstring). What it does not take over
    it leaves to ezdxf: an empty string draws nothing, and text inside a clipping
    boundary (a clipped block reference) is outlined so the clip applies to it.
    """
    global _text_pipeline_class
    if _text_pipeline_class is None:
        from ezdxf.addons.drawing.pipeline import RenderPipeline2d, prepare_string_for_rendering

        class _TextPipeline(RenderPipeline2d):
            def draw_text(self, text, transform, properties, cap_height, dxftype="TEXT"):
                face = properties.font or getattr(self, "default_font_face", None)
                if self.clipping_portal.is_active or face is None:
                    super().draw_text(text, transform, properties, cap_height, dxftype)
                    return
                if not text.strip():
                    return
                text = prepare_string_for_rendering(text, dxftype)
                try:
                    width = self.text_engine.get_text_line_width(text, face, cap_height)
                    descender = self.text_engine.get_font_measurements(face, cap_height).descender_height
                except (RuntimeError, ValueError):
                    # Where ezdxf cannot measure a string it cannot outline either, and draws nothing.
                    return
                # A row-vector Matrix44: x' = x*m00 + y*m10 + m30, y' = x*m01 + y*m11 + m31,
                # which is Canvas 2D's (a, b, c, d, e, f) read off in this order.
                linear = (transform[0, 0], transform[0, 1], transform[1, 0], transform[1, 1])
                offset = (transform[3, 0], transform[3, 1])
                self.backend.add_entity(
                    _TEXT,
                    (text, linear, offset, float(cap_height), float(width), float(descender), face),
                    self.get_backend_properties(properties),
                )

        _text_pipeline_class = _TextPipeline
    return _text_pipeline_class(backend)


def _render(document):
    """``(render context, ezdxf primitive dicts)`` for the modelspace."""
    from ezdxf.addons.drawing import RenderContext
    from ezdxf.addons.drawing.config import Configuration, LineweightPolicy
    from ezdxf.addons.drawing.frontend import UniversalFrontend
    from ezdxf.addons.drawing.json import CustomJSONBackend
    from ezdxf.addons.drawing.properties import LayerProperties, LayoutProperties

    modelspace = document.modelspace()
    context = RenderContext(document)
    fallback_layer = LayerProperties()
    fallback_layer.has_aci_color_7 = True
    context.layers = _DefaultPenLayers(context.layers, fallback_layer)

    backend = CustomJSONBackend()
    # ABSOLUTE lineweights keep the frontend from scaling strokes against a
    # page size we do not have. The widths are dropped from the payload anyway
    # (the client draws hairlines), but the policy must still be pinned or the
    # frontend reads a default that could change under us. (`Frontend` is this
    # same frontend over a plain `RenderPipeline2d`.)
    frontend = UniversalFrontend(
        context,
        _text_pipeline(backend),
        config=Configuration(lineweight_policy=LineweightPolicy.ABSOLUTE),
    )

    # The explicit layout properties are the point: without them ezdxf picks
    # the modelspace background and derives a foreground from it, and the
    # payload would encode that guess.
    layout_properties = LayoutProperties.from_layout(modelspace)
    layout_properties.set_colors(_SENTINEL_BACKGROUND, _DEFAULT_PEN_SENTINEL)
    with _seeded_randomness():
        frontend.draw_layout(modelspace, layout_properties=layout_properties)
    return context, backend.get_json_data()


@contextlib.contextmanager
def _seeded_randomness():
    """Pin the process's random stream for the length of one render.

    See ``_JIGGLE_SEED``. The lock serialises renders in a threaded server,
    which costs nothing real — a render is pure Python and holds the GIL for
    nearly all of its runtime anyway.
    """
    with _render_guard:
        state = random.getstate()
        random.seed(_JIGGLE_SEED)
        try:
            yield
        finally:
            random.setstate(state)


# --- geometry --------------------------------------------------------------


class _Extent:
    """The bounding box of the numbers actually emitted."""

    __slots__ = ("min_x", "min_y", "max_x", "max_y", "seen")

    def __init__(self) -> None:
        self.min_x = self.min_y = self.max_x = self.max_y = 0.0
        self.seen = False

    def add(self, x, y) -> None:
        if not self.seen:
            self.min_x = self.max_x = x
            self.min_y = self.max_y = y
            self.seen = True
            return
        if x < self.min_x:
            self.min_x = x
        elif x > self.max_x:
            self.max_x = x
        if y < self.min_y:
            self.min_y = y
        elif y > self.max_y:
            self.max_y = y

    def bounds(self):
        """``[minX, minY, maxX, maxY]``, or ``None`` when nothing was drawn.

        ``None`` rather than zeros: an empty modelspace has no extent, and
        ``[0,0,0,0]`` is a real (degenerate) box that a fit-to-bounds client
        would faithfully zoom to. Null says "there is nothing to fit to".
        """
        if not self.seen:
            return None
        return [self.min_x, self.min_y, self.max_x, self.max_y]


def _rounded(value):
    """One coordinate, rounded, integral when it can be.

    An int serialises shorter than the same float (``5`` vs ``5.0``) and is
    exact, which matters when a drawing carries a million of them. ``-0.0`` is
    folded to ``0`` so a value that differs only in sign of zero cannot make
    two payloads for the same drawing differ byte for byte.
    """
    number = round(float(value), _COORDINATE_DECIMALS)
    if number == 0.0:
        return 0
    integral = int(number)
    return integral if integral == number else number


def _point(coordinates, extent):
    x = _rounded(coordinates[0])
    y = _rounded(coordinates[1])
    extent.add(x, y)
    return [x, y]


def _lines(geometry, extent):
    out = []
    for line in geometry:
        x0 = _rounded(line[0])
        y0 = _rounded(line[1])
        x1 = _rounded(line[2])
        y1 = _rounded(line[3])
        extent.add(x0, y0)
        extent.add(x1, y1)
        out.append([x0, y0, x1, y1])
    return out


def _path(commands, extent):
    """An SVG-like command list.

    Bezier CONTROL points are counted into the extent as well as the on-curve
    points. The curve lies inside its control polygon, so the box is a
    conservative superset — never a box that clips geometry, which is the
    failure that matters for a fit-on-open.
    """
    out = []
    for command in commands:
        letter = command[0]
        numbers = []
        for index in range(1, len(command), 2):
            x = _rounded(command[index])
            y = _rounded(command[index + 1])
            extent.add(x, y)
            numbers.append(x)
            numbers.append(y)
        out.append([letter, *numbers])
    return out


def _polygon(vertices, extent):
    return [_point(vertex, extent) for vertex in vertices]


def _linear(value):
    """One coefficient of a text transform's linear part, rounded finer than a coordinate."""
    number = round(float(value), _LINEAR_DECIMALS)
    if number == 0.0:
        return 0
    integral = int(number)
    return integral if integral == number else number


class _Fonts:
    """The payload's ``fonts``: one row per face text is set in, in first-seen order.

    A row is what a client needs to name the face to its own font machinery —
    family, weight, italic — and nothing about where ezdxf found it: the file is
    this machine's, and the width every string is stretched to (``text``'s
    ``width``) already carries the layout ezdxf computed with it.
    """

    __slots__ = ("rows", "_index")

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._index: dict[tuple, int] = {}

    def of(self, face) -> int:
        family = str(getattr(face, "family", "") or "sans-serif")
        weight = int(getattr(face, "weight", 400) or 400)
        italic = bool(face.is_italic or face.is_oblique)
        key = (family, weight, italic)
        index = self._index.get(key)
        if index is None:
            index = self._index[key] = len(self.rows)
            self.rows.append({"family": family, "weight": weight, "italic": italic})
        return index


def _text(record, fonts, extent):
    """A ``text`` primitive's fields, its box counted into the extent.

    The box is the string's advance width by its cap height, down to the font's
    descender, put through the ROUNDED transform — the numbers a client draws
    with — so a fit to ``bounds`` holds the text it fits.
    """
    text, linear, offset, cap_height, width, descender, face = record
    a, b, c, d = (_linear(value) for value in linear)
    e, f = (_rounded(value) for value in offset)
    height = _rounded(cap_height)
    advance = _rounded(width)
    for x, y in ((0, -descender), (width, -descender), (width, cap_height), (0, cap_height)):
        _point((a * x + c * y + e, b * x + d * y + f), extent)
    return {
        "text": text,
        "font": fonts.of(face),
        "height": height,
        "width": advance,
        "transform": [a, b, c, d, e, f],
    }


def _geometry(primitive_type, geometry, extent):
    if primitive_type == "lines":
        return _lines(geometry, extent)
    if primitive_type == "point":
        return _point(geometry, extent)
    if primitive_type == "path":
        return _path(geometry, extent)
    if primitive_type == "filled-paths":
        return [_path(path, extent) for path in geometry]
    if primitive_type == "filled-polygon":
        return _polygon(geometry, extent)
    raise DrawingReadError(
        f"ezdxf emitted an unknown primitive type {primitive_type!r}; "
        "cadgen.drawing_payload needs a case for it before this drawing can be rendered"
    )


# --- colour ----------------------------------------------------------------


def _color(raw):
    """``#rrggbb``, or ``None`` for the drawing's default pen.

    Alpha is dropped. The payload's contract is an opaque pen colour per
    primitive; per-entity transparency is a separate feature and inventing a
    half-supported one here would be worse than not having it.
    """
    text = str(raw or "").strip().lower()
    if not text.startswith("#") or len(text) < 7:
        return None
    rgb = text[:7]
    return None if rgb == _DEFAULT_PEN_SENTINEL else rgb


def _layer_color(properties):
    """A LAYER table entry's own colour, or ``None`` when it is ACI 7."""
    if properties is None or getattr(properties, "has_aci_color_7", False):
        return None
    return _color(getattr(properties, "color", ""))


def _layers(context, primitives):
    """One row per layer that DREW something, in first-seen order.

    First-seen order rather than table order, for two reasons: a drawing's
    LAYER table routinely lists layers no entity uses (and a row with
    ``count: 0`` is noise), and first-seen order is the order a reader meets
    the geometry, so a legend built from it matches the drawing.
    """
    from ezdxf.addons.drawing.properties import layer_key

    counts: dict[str, int] = {}
    for primitive in primitives:
        name = str(primitive["properties"]["layer"])
        counts[name] = counts.get(name, 0) + 1
    return [
        {
            "name": name,
            "color": _layer_color(context.layers.get(layer_key(name))),
            "count": count,
        }
        # dicts preserve insertion order, which IS first-seen order here.
        for name, count in counts.items()
    ]


# --- units -----------------------------------------------------------------


def _units(document):
    """``$INSUNITS`` as a number, a name, and a factor to millimetres.

    ``toMillimetres`` is ``None`` for an unitless drawing (``$INSUNITS`` 0) and
    for any code ezdxf has no metric conversion for — a consumer must then
    treat the coordinates as bare drawing units rather than assume millimetres.
    """
    from ezdxf import units as ezdxf_units

    try:
        insunits = int(document.header.get("$INSUNITS", 0) or 0)
    except (TypeError, ValueError):
        insunits = 0
    try:
        name = str(ezdxf_units.unit_name(insunits))
    except (KeyError, IndexError, TypeError, ValueError):
        name = ""
    try:
        # Rounded: the table's inch factor is 25.400000000101603, and a payload
        # must not carry that as if the extra digits meant anything.
        factor = round(float(ezdxf_units.conversion_factor(insunits, ezdxf_units.MM)), 9)
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        factor = None
    return {"insunits": insunits, "name": name, "toMillimetres": factor}


# --- the payload -----------------------------------------------------------


def build_drawing_payload(path) -> dict:
    """The flat 2D render payload for one ``.dxf`` file.

    ``{schemaVersion, units, bounds, layers, fonts, primitives}``; see the
    module docstring for the coordinate, colour and text contracts.
    """
    document = read_drawing_document(path)
    context, emitted = _render(document)

    extent = _Extent()
    fonts = _Fonts()
    primitives = []
    for primitive in emitted:
        properties = primitive["properties"]
        primitive_type = str(primitive["type"])
        head = {
            "type": primitive_type,
            "layer": str(properties["layer"]),
            "color": _color(properties.get("color")),
        }
        if primitive_type == _TEXT:
            primitives.append({**head, **_text(primitive["geometry"], fonts, extent)})
        else:
            primitives.append({**head, "geometry": _geometry(primitive_type, primitive["geometry"], extent)})
    return {
        "schemaVersion": DRAWING_PAYLOAD_SCHEMA_VERSION,
        "units": _units(document),
        "bounds": extent.bounds(),
        "layers": _layers(context, emitted),
        "fonts": fonts.rows,
        "primitives": primitives,
    }


def encode_drawing_payload(payload) -> bytes:
    """The payload's exact bytes: compact, UTF-8, deterministic.

    ``allow_nan=False`` on purpose. A drawing that produced a non-finite
    coordinate would otherwise ship ``NaN``, which is not JSON and which every
    strict parser rejects at the client — far from the drawing that caused it.
    """
    try:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except ValueError as error:
        raise DrawingReadError(
            f"this drawing produced a coordinate that is not a finite number ({error}); "
            "check it for degenerate geometry (a zero-radius arc, a spline with "
            "coincident control points) in the program that made it"
        ) from None
    return text.encode("utf-8")


# --- the cached door -------------------------------------------------------


def drawing_extraction_scheme() -> str:
    """What this extraction IS, for the cache key.

    The payload's shape plus the ezdxf release that draws it: upgrading ezdxf
    changes flattening, font outlines and hatch patterns, so entries written by
    the old one must not be served. The version is read from distribution
    metadata rather than by importing ezdxf, so a cache HIT costs no import.
    """
    global _extraction_scheme
    if _extraction_scheme is None:
        from importlib.metadata import PackageNotFoundError, version

        try:
            ezdxf_version = str(version("ezdxf") or "")
        except PackageNotFoundError:
            import ezdxf

            ezdxf_version = str(ezdxf.__version__)
        _extraction_scheme = (
            f"cadgen-drawing-payload-v{DRAWING_PAYLOAD_SCHEMA_VERSION}+ezdxf-{ezdxf_version}"
        )
    return _extraction_scheme


def _document_hash(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def drawing_payload_key(path) -> str:
    """The store key of this file's payload: its bytes' hash under this extraction's scheme."""
    from cadgen.store import drawings as drawing_index

    try:
        return drawing_index.drawing_input_key(
            _document_hash(path), scheme=drawing_extraction_scheme()
        )
    except OSError as error:
        raise DrawingReadError(
            f"{Path(str(path)).name} could not be read ({error}); "
            "check that the file exists and that this user can read it"
        ) from None


def cached_drawing_payload(key: str) -> bytes | None:
    """The payload the store holds under ``key``, or ``None``: never a render."""
    from cadgen.store import drawings as drawing_index

    return drawing_index.read(key)


def render_drawing_payload(path, key: str) -> bytes:
    """Render the payload and keep it under ``key``. A store that cannot be
    written costs the cache, never the answer."""
    from cadgen.store import drawings as drawing_index

    data = encode_drawing_payload(build_drawing_payload(path))
    drawing_index.write(key, data)
    return data


def drawing_payload_bytes(path) -> bytes:
    """``encode_drawing_payload(build_drawing_payload(path))``, cached by content.

    The store answers for bytes it has already drawn, so re-opening a drawing
    — or opening one two tabs already have — never re-enters ezdxf. A store
    that cannot be read or written costs the cache, never the answer.
    """
    key = drawing_payload_key(path)
    cached = cached_drawing_payload(key)
    if cached is not None:
        return cached
    return render_drawing_payload(path, key)
