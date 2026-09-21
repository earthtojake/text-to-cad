"""A DXF flattened into a 2D render payload by ezdxf's drawing add-on.

One function does the work: ``ezdxf``'s ``Frontend`` walks the modelspace and
hands a backend the primitives every entity reduces to — text outlined to
filled paths, dimensions exploded to their lines and arrow heads, hatches to
fills or pattern lines, block references to the geometry of their contents.
Nothing here knows about LINE or ARC or HATCH; the add-on already resolved all
of that, which is the whole reason this module is 400 lines instead of 4000.

Coordinates are DXF modelspace coordinates, **y up**, rounded to
``_COORDINATE_DECIMALS`` places. Rounding is not cosmetic: a flat pattern's
payload shrinks ~3x, and the rounded numbers are also what ``bounds`` is
computed from, so a consumer that fits the view to ``bounds`` fits it to the
geometry it will actually draw.

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
even imports it.
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
    "drawing_extraction_scheme",
    "drawing_payload_bytes",
    "encode_drawing_payload",
    "read_drawing_document",
]

# Bumped when the payload's SHAPE changes. It rides in the payload (a client
# checks it before drawing) and in the cache key (an old shape is not served
# from the store after an upgrade).
DRAWING_PAYLOAD_SCHEMA_VERSION = 1

# The layout foreground handed to ezdxf, and therefore the exact colour every
# default-pen primitive comes back wearing. Not in the ACI palette; see the
# module docstring.
_DEFAULT_PEN_SENTINEL = "#010203"
# The background only decides which foreground ezdxf would have guessed, and we
# do not let it guess. It is still pinned so nothing downstream varies with it.
_SENTINEL_BACKGROUND = "#ffffff"

_COORDINATE_DECIMALS = 4

# ezdxf's own primitive names, unchanged: "point", "lines", "path",
# "filled-paths", "filled-polygon". Renaming them would create a second
# vocabulary for one set of shapes.

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


def _render(document):
    """``(render context, ezdxf primitive dicts)`` for the modelspace."""
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import Configuration, LineweightPolicy
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
    # frontend reads a default that could change under us.
    frontend = Frontend(
        context, backend, config=Configuration(lineweight_policy=LineweightPolicy.ABSOLUTE)
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

    ``{schemaVersion, units, bounds, layers, primitives}``; see the module
    docstring for the coordinate and colour contracts.
    """
    document = read_drawing_document(path)
    context, emitted = _render(document)

    extent = _Extent()
    primitives = []
    for primitive in emitted:
        properties = primitive["properties"]
        primitive_type = str(primitive["type"])
        primitives.append(
            {
                "type": primitive_type,
                "layer": str(properties["layer"]),
                "color": _color(properties.get("color")),
                "geometry": _geometry(primitive_type, primitive["geometry"], extent),
            }
        )
    return {
        "schemaVersion": DRAWING_PAYLOAD_SCHEMA_VERSION,
        "units": _units(document),
        "bounds": extent.bounds(),
        "layers": _layers(context, emitted),
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


def drawing_payload_bytes(path) -> bytes:
    """``encode_drawing_payload(build_drawing_payload(path))``, cached by content.

    The store answers for bytes it has already drawn, so re-opening a drawing
    — or opening one two tabs already have — never re-enters ezdxf. A store
    that cannot be read or written costs the cache, never the answer.
    """
    from cadgen.store import drawings as drawing_index

    try:
        key = drawing_index.drawing_input_key(
            _document_hash(path), scheme=drawing_extraction_scheme()
        )
    except OSError as error:
        raise DrawingReadError(
            f"{Path(str(path)).name} could not be read ({error}); "
            "check that the file exists and that this user can read it"
        ) from None

    cached = drawing_index.read(key)
    if cached is not None:
        return cached
    data = encode_drawing_payload(build_drawing_payload(path))
    drawing_index.write(key, data)
    return data
