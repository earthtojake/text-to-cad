"""Native 2D board stills: read the saved file on each draw, rasterize its plot, discard it.

No XCAF document, model worker, browser, KiCad process or parsed-board cache is involved.
The plot and Display contract are the viewer's, and so is the drawing: this paints a plot as
``@cad/core``'s ``plot2d`` draws it (``plot.js``, ``theme.js``) -- KiCad's canvas, its
drawing order, its colours and zone opacity, plated holes seen through, a label once the
view reads it, a track's net name laid out along it as the view's size places it -- with
Pillow; the engine's existing annotation painter paints the same sheet coordinates.
"""
from __future__ import annotations

import io
import math
import re
import time
from pathlib import Path
from typing import Any

MODES = {
    "board": {"area", "copper", "mask", "paste", "silk", "fab", "courtyard", "adhesive", "user", "margin", "via", "drill",
              "outline", "ratsnest", "names"},
    "copper": {"area", "copper", "via", "drill", "outline", "ratsnest", "names"},
    "assembly": {"area", "silk", "fab", "courtyard", "drill", "outline", "ratsnest"},
    "placement": {"area", "fab", "courtyard", "outline"},
}
DISPLAY_KEYS = {"mode", "side", "poured", "layers", "appearance", "active", "dim", "zones", "tracks"}
# What a set saved when a board had a drawing sheet may still name: no layer now, left out.
GONE = {"sheet"}
# Mirrors core/lib/plot2d/theme.js, both themes; snapshot pixel tests check the layer colours. Dark is KiCad's
# default theme on the viewer's neutral dark canvas; light is each of its colours darkened, its hue kept, to read
# at 3:1 on white (theme.js says how). ``appearance`` picks one, light by default, as every snapshot's does.
INNER = ["#7FC87F", "#CE7D2C", "#4FCBCB", "#DB628B", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#8DCB81", "#ED7C33",
         "#5BC3EB", "#F76F8E", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#ED7C33", "#5BC3EB", "#F76F8E", "#A7A5C6",
         "#28CCD9", "#E8B2A7", "#F2EDA1", "#ED7C33", "#5BC3EB", "#F76F8E", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1"]
COLORS = {
    "F.Cu": "#C83434", "B.Cu": "#4D7FC4", "F.SilkS": "#F2EDA1", "B.SilkS": "#E8B2A7",
    "F.Fab": "#AFAFAF", "B.Fab": "#585D84", "F.CrtYd": "#FF26E2", "B.CrtYd": "#26E9FF",
    "F.Mask": (216, 100, 255, 0.4), "B.Mask": (2, 255, 238, 0.4),
    "F.Paste": (180, 160, 154, 0.9), "B.Paste": (0, 194, 194, 0.9),
    "F.Adhes": "#840084", "B.Adhes": "#000084", "Edge.Cuts": "#D0D2CD", "Margin": "#FF26E2",
    "Dwgs.User": "#C2C2C2", "Cmts.User": "#5994DC", "Eco1.User": "#B4DBD2", "Eco2.User": "#D8C852",
    "User.1": "#C2C2C2", "User.2": "#5994DC", "User.3": "#B4DBD2", "User.4": "#D8C852", "User.5": "#C2C2C2",
    "User.6": "#5994DC", "User.7": "#B4DBD2", "User.8": "#D8C852", "User.9": "#E8B2A7",
    "vias": "#E3B72E", "ratsnest": (0, 248, 255, 0.35), "drills": "#E3B72E",
    "area": (100, 100, 100, 0.35), "names": (255, 255, 255, 0.9),
}
LIGHT_INNER = ["#5BA35C", "#CE7D2C", "#14A5A5", "#DB628B", "#9391B1", "#03A3AE", "#BC887E", "#9C964D", "#67A35B", "#E6762B",
               "#32A0C7", "#EE6786", "#9391B1", "#03A3AE", "#BC887E", "#9C964D", "#E6762B", "#32A0C7", "#EE6786", "#9391B1",
               "#03A3AE", "#BC887E", "#9C964D", "#E6762B", "#32A0C7", "#EE6786", "#9391B1", "#03A3AE", "#BC887E", "#9C964D"]
LIGHT_COLORS = {
    **COLORS, "F.SilkS": "#9C964D", "B.SilkS": "#BC887E", "F.Fab": "#939393", "B.CrtYd": "#0AA3B4",
    "F.Mask": (213, 97, 252, 0.4), "B.Mask": (15, 166, 155, 0.4), "F.Paste": (163, 143, 137, 0.9), "B.Paste": (21, 164, 164, 0.9),
    "Edge.Cuts": "#939590", "Dwgs.User": "#939393", "Eco1.User": "#769B93", "Eco2.User": "#A59503",
    "User.1": "#939393", "User.3": "#769B93", "User.4": "#A59503", "User.5": "#939393", "User.7": "#769B93", "User.8": "#A59503",
    "User.9": "#BC887E", "vias": "#B58F0E", "ratsnest": (20, 164, 169, 0.6), "drills": "#B58F0E", "area": (0, 0, 0, 0.07),
}
ZONE_OPACITY = 0.6
# KiCad's "Inactive layers: Dim": every layer but the active one at this share (plot2d's DIM_OPACITY).
DIM_OPACITY = 0.3
# What may be the active layer: a board layer, not the area or what goes through the board.
#: The room a still's fit leaves round the board, as the board view's (plot2d's ``boardFitMargin``):
#: this share of the still's smaller side, never less than this many CSS pixels.
BOARD_FIT_MARGIN_SHARE = 0.06
BOARD_FIT_MARGIN_PX = 16
ACTIVE_KINDS = {"copper", "mask", "paste", "silk", "fab", "courtyard", "adhesive", "user", "margin", "outline"}
# A hole's fill and its plated wall (None: the board's background, seen through).
HOLES = {"pad": (None, "#E3B72E"), "via": ("#E3B72E", "#ECECEC"), "npth": ("#1AC4D2", None)}
LIGHT_HOLES = {"pad": (None, "#B58F0E"), "via": ("#B58F0E", "#949494"), "npth": ("#0BA3B0", None)}
NAMES = {"pad": (255, 255, 255, 0.9), "via": (50, 50, 50, 0.9)}
#: Each appearance's canvas, its layers and its holes (theme.js's ``BOARD_PALETTES``).
PALETTES = {
    "dark": {"background": "#292929", "colors": COLORS, "inner": INNER, "holes": HOLES},
    "light": {"background": "#FFFFFF", "colors": LIGHT_COLORS, "inner": LIGHT_INNER, "holes": LIGHT_HOLES},
}
UNDERLAYS = {"area"}
# Placement's airwires, as the overlay draws them (board2d/boardOverlay.js's ``airwire``): light on dark, dark on light.
AIRWIRES = {"dark": (232, 238, 245, 0.8), "light": (80, 86, 94, 0.8)}
OVERLAYS = {"drill", "via", "ratsnest", "names"}


def display_options(value: Any, grid: bool = False) -> dict:
    from cad.engine.snapshot import SnapshotRefused, _json_or_file

    if isinstance(value, str):
        if value.lstrip().startswith("{") or value.endswith(".json"):
            value = _json_or_file(value, "--display")
        else:
            # A mode, an appearance, or both by commas (``copper,dark``), as every snapshot's --display takes them.
            tokens = [token.strip() for token in value.split(",") if token.strip()]
            value = {}
            for token in tokens:
                key = "appearance" if token in ("light", "dark") else "mode"
                if key in value:
                    raise SnapshotRefused(f"--display {value!r} names one mode and one appearance (light or dark), by commas")
                value[key] = token
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - DISPLAY_KEYS or grid:
        raise SnapshotRefused(f"a board's display takes {', '.join(sorted(DISPLAY_KEYS))}")
    display = {"mode": "board", "side": "top", "poured": True, "layers": None, "appearance": "light", "active": None, "dim": False,
               "zones": ZONE_OPACITY, "tracks": 1.0, **value}
    if display["mode"] not in MODES:
        raise SnapshotRefused(f"a board's modes are {', '.join(MODES)}")
    if display["side"] not in ("top", "bottom") or type(display["poured"]) is not bool:
        raise SnapshotRefused("board side is top or bottom and poured is true or false")
    if display["appearance"] not in ("light", "dark"):
        raise SnapshotRefused("board appearance is light or dark")
    if display["active"] is not None and (not isinstance(display["active"], str) or not display["active"]) or type(display["dim"]) is not bool:
        raise SnapshotRefused("board active is a layer id or null, and dim is true or false")
    for key in ("zones", "tracks"):
        if isinstance(display[key], bool) or not isinstance(display[key], (int, float)) or not 0 <= display[key] <= 1:
            raise SnapshotRefused(f"board {key} is an opacity from 0 to 1")
    layers = display["layers"]
    if layers is not None and (not isinstance(layers, list) or not all(isinstance(x, str) and x for x in layers)):
        raise SnapshotRefused("board layers is a list of layer ids")
    if layers is not None:
        display["layers"] = [layer for layer in layers if layer not in GONE]
    return display


def refusals(still: Any, name: str) -> None:
    from cad.engine.snapshot import SnapshotRefused
    from cad.engine.render.drawing import plan_view

    display_options(still.display)
    if still.preview or still.pose is not None or still.transparent:
        raise SnapshotRefused(f"{name} is a flat board: Preview, pose and transparent output are not supported")
    if still.camera is not None:
        plan_view(still.camera, name)


def _rgba(color) -> tuple[int, int, int, int]:
    """A theme colour (``#rrggbb`` or ``(r, g, b, alpha)``) as Pillow's RGBA."""
    if isinstance(color, tuple):
        return color[0], color[1], color[2], round(color[3] * 255)
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), 255


def layer_color(layer: str, appearance: str = "dark"):
    palette = PALETTES[appearance]
    inner = re.fullmatch(r"In(\d+)\.Cu", layer)
    if inner:
        return palette["inner"][(int(inner[1]) - 1) % len(palette["inner"])]
    return palette["colors"].get(layer, palette["colors"]["Dwgs.User"])


def netname_color(layer: str, appearance: str = "dark"):
    """theme.js's ``netnameColor``: white names on copper, or dark ones on copper bright enough."""
    color = layer_color(layer, appearance)
    if isinstance(color, tuple):
        return (255, 255, 255, 0.7)
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return (0, 0, 0, 0.7) if r * 0.299 + g * 0.587 + b * 0.117 > 0.5 else (255, 255, 255, 0.7)


def item_color(layer: str, item: dict, appearance: str = "dark"):
    if item["t"] == "label":
        return NAMES.get(item.get("kind"), NAMES["pad"]) if layer == "names" else netname_color(layer, appearance)
    return layer_color(layer, appearance)


def grown_outline(points, distance: float) -> list:
    """plot.js's ``grownOutline``: a convex outline grown by ``distance``, its corners round."""
    count = len(points)
    area = sum(points[i][0] * points[(i + 1) % count][1] - points[(i + 1) % count][0] * points[i][1] for i in range(count))
    sign = 1 if area > 0 else -1

    def normal(a, b):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        return (sign * (b[1] - a[1]) / length, -sign * (b[0] - a[0]) / length) if length > 1e-12 else None

    out, previous = [], None
    for index in range(count):
        if previous is not None:
            break
        previous = normal(points[index - 1], points[index])
    for index in range(count):
        here = points[index]
        following = normal(here, points[(index + 1) % count])
        if following is None:
            continue
        start = math.atan2(previous[1], previous[0])
        sweep = math.atan2(following[1], following[0]) - start
        while sign * sweep < 0:
            sweep += sign * math.pi * 2
        if abs(sweep) > math.pi:
            sweep -= sign * math.pi * 2
        steps = max(1, math.ceil(abs(sweep) / (math.pi / 8)))
        out.extend((here[0] + distance * math.cos(start + sweep * k / steps), here[1] + distance * math.sin(start + sweep * k / steps))
                   for k in range(steps + 1))
        previous = following
    return out


def viewed_layers(layers: list[dict], display: dict) -> list[dict]:
    """plot2d's ``viewedLayers`` over the Display: its layers, the board's stack reversed from below."""
    if display["layers"] is not None:
        kept = [layer for layer in layers if layer["id"] in display["layers"]]
    else:
        kept = [layer for layer in layers if layer["kind"] in MODES[display["mode"]]]
    stack = [x for x in kept if x["kind"] not in OVERLAYS and x["kind"] not in UNDERLAYS]
    if display["side"] == "bottom":
        stack.reverse()
    # The active layer tops the board's stack, as plot2d draws it.
    stack.sort(key=lambda x: x["id"] == display.get("active"))
    return [x for x in kept if x["kind"] in UNDERLAYS] + stack + [x for x in kept if x["kind"] in OVERLAYS]


def active_layer(layers: list[dict], display: dict) -> str | None:
    """plot2d's ``boardActiveLayer``: the one chosen, while the board has it, else the copper facing the eye."""
    ids = {layer["id"]: layer["kind"] for layer in layers}
    if display.get("active") and ids.get(display["active"]) in ACTIVE_KINDS:
        return display["active"]
    facing = "B.Cu" if display["side"] == "bottom" else "F.Cu"
    return facing if facing in ids else None


class _Painter:
    """One frame of a plot on a Pillow image, as ``plot2d.drawPlot`` paints it on a canvas."""

    def __init__(self, image, place, scale: float, ss: int, background: str, appearance: str = "dark"):
        from PIL import Image, ImageDraw

        self.Image, self.ImageDraw = Image, ImageDraw
        self.image = image
        self.pen = ImageDraw.Draw(image, "RGBA")
        self.place, self.scale, self.ss, self.background = place, scale, ss, background
        self.appearance = appearance
        self.batch = None  # a translucent colour's mask, painted in one pass: (rgba, mask, pen)

    # -- translucent paint: one mask per run of a colour, composited once, so it never doubles up on itself

    def target(self, color, opacity: float = 1.0):
        rgba = _rgba(color)
        alpha = round(rgba[3] * opacity)
        if alpha >= 255:
            self.flush()
            return self.pen, rgba
        key = (rgba[:3], alpha)
        if self.batch is None or self.batch[0] != key:
            self.flush()
            mask = self.Image.new("L", self.image.size, 0)
            self.batch = (key, mask, self.ImageDraw.Draw(mask))
        return self.batch[2], 255

    def flush(self):
        if self.batch is None:
            return
        (rgb, alpha), mask, _pen = self.batch
        self.batch = None
        layer = self.Image.new("RGB", self.image.size, rgb)
        self.image.paste(layer, (0, 0), mask.point(lambda value: value * alpha // 255))

    # -- primitives

    def line(self, points, color, wide, *, closed=False, opacity=1.0, minimum=True):
        if len(points) < 2:
            return
        pts = [self.place(p) for p in points]
        if closed:
            pts.append(pts[0])
        width = wide * self.scale
        if minimum:
            width = max(width, self.ss)  # never thinner than an output pixel (KiCad's minimum line width)
        width = max(1, round(width))
        pen, fill = self.target(color, opacity)
        pen.line(pts, fill=fill, width=width, joint="curve")
        if width > 2:
            r = width / 2
            for x, y in pts:
                pen.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    def pairs(self, points, color, opacity=1.0):
        pen, fill = self.target(color, opacity)
        for a, b in zip(points[0::2], points[1::2]):
            pen.line([self.place(a), self.place(b)], fill=fill, width=self.ss)

    def polygon(self, points, color, *, holes=(), opacity=1.0, outline=0.0):
        pts = [self.place(p) for p in points]
        if holes:
            self.flush()
            mask = self.Image.new("L", self.image.size, 0)
            draw = self.ImageDraw.Draw(mask)
            draw.polygon(pts, fill=255)
            for ring in holes:
                draw.polygon([self.place(p) for p in ring], fill=0)
            rgba = _rgba(color)
            alpha = round(rgba[3] * opacity)
            self.image.paste(self.Image.new("RGB", self.image.size, rgba[:3]), (0, 0), mask.point(lambda value: value * alpha // 255))
            return
        pen, fill = self.target(color, opacity)
        pen.polygon(pts, fill=fill)
        if outline > 0:
            width = max(1, round(outline * self.scale))
            pen.line([*pts, pts[0]], fill=fill, width=width, joint="curve")

    def knockout(self, item: dict, color):
        """Knocked-out text: its box in ``color``, the letters cut from it, what lies under seen through them."""
        self.flush()
        mask = self.Image.new("L", self.image.size, 0)
        draw = self.ImageDraw.Draw(mask)
        draw.polygon([self.place(p) for p in item["knockout"]], fill=255)
        width = max(1, round(item.get("w", 0) * self.scale))
        for stroke in item["strokes"]:
            pts = [self.place(p) for p in stroke]
            draw.line(pts, fill=0, width=width, joint="curve")
            for x, y in pts:
                draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=0)
        rgba = _rgba(color)
        self.image.paste(self.Image.new("RGB", self.image.size, rgba[:3]), (0, 0), mask.point(lambda value: value * rgba[3] // 255))

    def disc(self, at, radius, color, *, ring=0.0, start=None, end=None):
        x, y = self.place(at)
        r = radius * self.scale
        pen, fill = self.target(color)
        if ring:
            width = max(1, round(ring * self.scale))
            pen.ellipse((x - r - width / 2, y - r - width / 2, x + r + width / 2, y + r + width / 2), outline=fill, width=width)
        elif start is not None:
            pen.pieslice((x - r, y - r, x + r, y + r), start, end, fill=fill)
        else:
            pen.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    # -- items

    def hole(self, item: dict):
        holes = PALETTES[self.appearance]["holes"]
        fill, wall = holes.get(item["hole"], holes["npth"])
        fill = fill or self.background
        if item["t"] == "circle":
            if item.get("w", 0) > 0 and wall:
                self.disc(item["at"], item["r"] + item["w"], wall)
            span = item.get("span")
            if span and len(span) == 2:
                # plot.js: the half on top of the screen is the via's top layer, the other its bottom.
                self.disc(item["at"], item["r"], layer_color(span[0], self.appearance), start=180, end=360)
                self.disc(item["at"], item["r"], layer_color(span[1], self.appearance), start=0, end=180)
                return
            self.disc(item["at"], item["r"], fill)
            return
        if item.get("w", 0) > 0 and wall:
            self.line(item["pts"], wall, item["w"] * 2, closed=True)
        self.polygon(item["pts"], fill)

    def layer(self, layer: dict, *, poured: bool, vias: bool, names: bool, mirrored: bool, viewport: tuple[float, float],
              zones: float = ZONE_OPACITY, tracks: float = 1.0):
        from cad.engine.formats.kicad.labels import is_track, track_labels, track_name_detail
        from cad.engine.formats.kicad.stroke_font import text_strokes

        color = layer_color(layer["id"], self.appearance)
        copper = layer["kind"] == "copper"
        detail = self.scale / self.ss
        named = []  # the tracks whose net names this frame writes, over everything else on their copper
        for item in layer["items"]:
            if item.get("pour") and not poured:
                continue
            if (not vias and item.get("via") and not item.get("hole")) or (not names and item["t"] == "label"):
                continue
            if copper and names and is_track(item) and detail >= track_name_detail(item["w"]):
                named.append(item)
            if item.get("hole"):
                self.hole(item)
                continue
            kind = item["t"]
            if kind == "label":
                if detail < item.get("lod", 0):
                    continue
                strokes = text_strokes(item["text"], size=item["size"], at=item["at"], angle=item.get("angle", 0.0), mirror=mirrored)
                for stroke in strokes:
                    self.line(stroke, item_color(layer["id"], item, self.appearance), item.get("w", 0), minimum=False)
                continue
            paint = color
            if item.get("knockout"):
                self.knockout(item, paint)
                continue
            if item.get("clearance", 0) > 0:
                self.line(grown_outline(item["pts"], item["clearance"]), paint, 0, closed=True)
            opacity = zones if item.get("pour") and not item.get("teardrop") else tracks if copper and is_track(item) else 1.0
            wide = item.get("w", 0)
            if kind == "poly":
                outline = max(wide, self.ss / self.scale) if copper and item.get("ref") else wide
                self.polygon(item["pts"], paint, holes=item.get("holes") or (), opacity=opacity, outline=outline)
            elif kind == "circle":
                if wide:
                    self.disc(item["at"], item["r"], paint, ring=max(wide, 0 if copper else self.ss / self.scale))
                else:
                    self.disc(item["at"], item["r"], paint)
            elif kind == "text":
                for stroke in item["strokes"]:
                    self.line(stroke, paint, wide)
            elif item.get("pairs"):
                self.pairs(item["pts"], paint, opacity)
            else:
                self.line(item["pts"], paint, wide, closed=item.get("closed", False), opacity=opacity, minimum=not copper or not wide)
        for item in named:
            for label in track_labels(item, viewport):
                strokes = text_strokes(label["text"], size=label["size"], at=label["at"], angle=label["angle"], mirror=mirrored)
                for stroke in strokes:
                    self.line(stroke, netname_color(layer["id"], self.appearance), label["w"], minimum=False)
        self.flush()


class Held:
    """A render-service handle containing only the file path, never the parsed board."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.kind = "kicad_pcb"
        self.files: dict = {}
        self.warnings: list[str] = []

    def open(self):
        from cad.engine.formats import files_of
        self.files = files_of([str(self.path)])
        return {"kind": self.kind, "files": self.files, "warnings": self.warnings, "readMs": 0}

    def close(self):
        pass

    def draw(self, still: Any):
        import numpy as np
        from PIL import Image
        from cad.engine.formats.kicad.poured import plot as poured_plot
        from cad.engine.render.drawing import paint_ink, plan_view
        from cad.engine.render.overlay import REFERENCE_HEIGHT, paint_measurements
        from cad.engine.render.service import finished
        from cad.engine.snapshot import SnapshotRefused

        started = time.perf_counter()
        refusals(still, self.path.name)
        display = display_options(still.display)
        # The pours KiCad refilled, as the viewer draws them: what the engine kept for these bytes (``poured``).
        payload = poured_plot(self.path)
        pours = payload.get("pours") or {}
        if not pours.get("refilled") and pours.get("warning") and pours["warning"] not in self.warnings:
            self.warnings.append(pours["warning"])
        sheet = payload["sheets"][0]
        layers = sheet["layers"]
        if display["layers"] is not None:
            unknown = set(display["layers"]) - {layer["id"] for layer in layers}
            if unknown:
                raise SnapshotRefused(f"unknown board layers: {', '.join(sorted(unknown))}")
        layers = viewed_layers(layers, display)
        bottom = display["side"] == "bottom"
        # Fixed supersampling smooths native strokes; renderScale still names the requested output.
        ss = 2
        width, height = (n * ss for n in still.drawn)
        if still.camera is not None:
            cx, cy, half = plan_view(still.camera, self.path.name)
            scale = height / (2 * half)
        else:
            # The board view's fit (plot2d's ``boardFitMargin``): 6% of the still's smaller side a side,
            # never under 16px; a still has no tool strip over it to clear.
            cx, cy = sheet["width"] / 2, -sheet["height"] / 2
            margin = max(BOARD_FIT_MARGIN_PX * ss, BOARD_FIT_MARGIN_SHARE * min(width, height))
            scale = min(max(width - 2 * margin, width / 2) / max(sheet["width"], 1e-9),
                        max(height - 2 * margin, height / 2) / max(sheet["height"], 1e-9))

        def place(point):
            x = sheet["width"] - point[0] if bottom else point[0]
            return ((x - cx) * scale + width / 2, (point[1] + cy) * scale + height / 2)

        # The canvas of the still's appearance, everywhere (the payload's own is the dark one).
        appearance = display["appearance"]
        background = PALETTES[appearance]["background"]
        image = Image.new("RGB", (width, height), background)
        named = set(display["layers"]) if display["layers"] is not None else None
        vias, names = named is None or "vias" in named, named is None or "names" in named
        viewport = (width / scale, height / scale)  # the millimetres the still shows, for where a track's names fall
        # Dim: every layer but the active one and the board's area is blended over what lies under it at DIM_OPACITY.
        kept = active_layer(sheet["layers"], display) if display["dim"] else None
        for layer in layers:
            faded = kept is not None and layer["id"] != kept and layer["kind"] not in UNDERLAYS
            under = image.copy() if faded else None
            _Painter(image, place, scale, ss, background, appearance).layer(
                layer, poured=display["poured"], vias=vias, names=names, mirrored=bottom, viewport=viewport,
                zones=display["zones"], tracks=display["tracks"])
            if faded:
                image = Image.blend(under, image, DIM_OPACITY)
        if display["mode"] == "placement":
            from PIL import ImageDraw

            airwires = _Painter(image, place, scale, ss, background, appearance)
            _placement(ImageDraw.Draw(image, "RGBA"), payload["board"], place, scale, bottom, airwires.line, appearance)
            airwires.flush()
        warnings = list(self.warnings)
        if still.references:  # what the prompt named, lit as the viewer lit it (`board_refs.py`)
            from PIL import ImageDraw

            from cad.engine.render.board_refs import paint_references

            warnings += paint_references(ImageDraw.Draw(image, "RGBA"), self.path, still.references,
                                         payload["board"]["origin"], place, scale, ss, appearance=appearance)
        frame = np.array(image)
        if still.annotation:
            paint_ink(frame, still.annotation.get("marks", []), place, height / REFERENCE_HEIGHT)
        if still.measurements:
            paint_measurements(frame, still.measurements, lambda points: np.array([place(p) for p in points]))
        image = Image.fromarray(frame).resize(still.size, Image.Resampling.LANCZOS)
        output = io.BytesIO(); image.save(output, format="PNG")
        return output.getvalue(), {"kind": self.kind, "renderer": "pillow", "width": still.size[0], "height": still.size[1],
            "camera": "plan" if still.camera is not None else "top", "projection": "orthographic", "displayMode": display["mode"],
            "preview": False, "boardDisplay": display, "warnings": warnings, **finished(still), "timings": {"renderMs": round((time.perf_counter()-started)*1000)}}


def _placement(pen, board, place, scale, bottom, line, appearance="dark"):
    """Placement's pads and all unpoured net connections, as the board overlay draws them."""
    pads = board["pads"]
    near = "bottom" if bottom else "top"
    pads = sorted(pads, key=lambda pad: pad["side"] in (near, "both"))
    for pad in pads:
        polygon = pad["polygon"]
        color = (77, 127, 196, 230) if pad["side"] == "bottom" or (pad["side"] == "both" and bottom) else (200, 52, 52, 230)
        if len(polygon) > 2:
            pen.polygon([place(p) for p in polygon], fill=color)
    for hole in [*pads, *board["holes"]]:
        radius = (hole.get("drill") or hole.get("diameter", 0)) * scale / 2
        if radius:
            x, y = place(hole["at"])
            pen.ellipse((x-radius, y-radius, x+radius, y+radius), fill="black")
    nets = {}
    pins = set()
    for pad in board["pads"]:
        pin = (pad["part"], pad["number"])
        if pad.get("net") and pad.get("at") and pin not in pins:
            pins.add(pin)
            nets.setdefault(pad["net"], []).append(pad["at"])
    poured = {zone["net"] for zone in board.get("zones", []) if zone.get("net")}
    for name, points in nets.items():
        if name in poured or len(points) < 2:
            continue
        # Prim's O(n²) tree, matching core/board2d/airwires.js, one endpoint per logical pin.
        joined = set()
        distance = [math.inf] * len(points)
        parents = [-1] * len(points)
        distance[0] = 0
        for _ in points:
            next_pin = min((i for i in range(len(points)) if i not in joined), key=distance.__getitem__)
            joined.add(next_pin)
            if parents[next_pin] >= 0:
                line([points[parents[next_pin]], points[next_pin]], AIRWIRES[appearance], 0)
            for i, point in enumerate(points):
                if i not in joined:
                    length = math.dist(point, points[next_pin])
                    if length < distance[i]:
                        distance[i], parents[i] = length, next_pin
