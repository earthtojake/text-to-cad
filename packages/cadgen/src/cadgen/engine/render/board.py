"""Native 2D board stills: read the saved file on each draw, rasterize its plot, discard it.

No XCAF document, model worker, browser, KiCad process or parsed-board cache is involved.
The plot and Display contract are the viewer's; Pillow paints the flat primitives and the
engine's existing annotation painter paints the same sheet coordinates.
"""
from __future__ import annotations

import io
import math
import re
import time
from pathlib import Path
from typing import Any

MODES = {
    "board": {"copper", "mask", "paste", "silk", "fab", "adhesive", "user", "margin", "via", "drill", "outline", "ratsnest"},
    "copper": {"copper", "via", "drill", "outline", "ratsnest"},
    "assembly": {"silk", "fab", "courtyard", "drill", "outline", "ratsnest"},
    "placement": {"fab", "courtyard", "outline"},
}
DISPLAY_KEYS = {"mode", "side", "poured", "layers", "appearance"}
# Mirrors core/lib/plot2d/theme.js; snapshot pixel tests check the layer colours.
INNER = ["#7FC87F", "#CE7D2C", "#4FCBCB", "#DB628B", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#8DCB81", "#ED7C33",
         "#5BC3C3", "#D379A6", "#B0B0B0", "#3FC9E8", "#F0A388", "#F3EC75", "#61B363", "#FF8342", "#5BB7B5", "#C86D9A",
         "#C8C8C8", "#2FB7D6", "#F68661", "#E5DE45", "#58A456", "#F8925B", "#44B4AE", "#C36491", "#818181", "#1FA4C5"]
COLORS = {
    "F.Cu": "#C83434", "B.Cu": "#4D7FC4", "F.SilkS": "#F2EDA1", "B.SilkS": "#E8B2A7",
    "F.Fab": "#AFAFAF", "B.Fab": "#585D84", "F.CrtYd": "#FF26E2", "B.CrtYd": "#26E9FF",
    "F.Mask": (216, 100, 255, 102), "B.Mask": (2, 255, 238, 102),
    "F.Paste": (180, 160, 154, 230), "B.Paste": (0, 194, 194, 230),
    "F.Adhes": "#840084", "B.Adhes": "#000084", "Edge.Cuts": "#D0D2CD", "Margin": "#FF26E2",
    "Dwgs.User": "#C2C2C2", "Cmts.User": "#5994DC", "Eco1.User": "#B4DBD2", "Eco2.User": "#D8C852",
    "User.1": "#C2C2C2", "User.2": "#5994DC", "User.3": "#B4DBD2", "User.4": "#D8C852", "User.5": "#C2C2C2",
    "User.6": "#5994DC", "User.7": "#B4DBD2", "User.8": "#D8C852", "User.9": "#E8B2A7",
    "vias": "#ECECEC", "ratsnest": (245, 255, 213, 179), "drills": "#C2C200",
}
VIAS = {"through": "#ECECEC", "blind": "#BB9726", "micro": "#008484"}
HOLES = {"pad": "#C2C200", "via": "#E3B72E", "npth": "#1AC4D2"}
OVERLAYS = {"outline", "via", "ratsnest", "drill"}


def display_options(value: Any, grid: bool = False) -> dict:
    from cadgen.engine.snapshot import SnapshotRefused, _json_or_file

    if isinstance(value, str):
        value = _json_or_file(value, "--display") if value.lstrip().startswith("{") or value.endswith(".json") else {"mode": value}
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - DISPLAY_KEYS or grid:
        raise SnapshotRefused(f"a board's display takes {', '.join(sorted(DISPLAY_KEYS))}")
    display = {"mode": "board", "side": "top", "poured": True, "layers": None, "appearance": "light", **value}
    if display["mode"] not in MODES:
        raise SnapshotRefused(f"a board's modes are {', '.join(MODES)}")
    if display["side"] not in ("top", "bottom") or type(display["poured"]) is not bool:
        raise SnapshotRefused("board side is top or bottom and poured is true or false")
    if display["appearance"] not in ("light", "dark"):
        raise SnapshotRefused("board appearance is light or dark")
    layers = display["layers"]
    if layers is not None and (not isinstance(layers, list) or not all(isinstance(x, str) and x for x in layers)):
        raise SnapshotRefused("board layers is a list of layer ids")
    return display


def refusals(still: Any, name: str) -> None:
    from cadgen.engine.snapshot import SnapshotRefused
    from cadgen.engine.render.drawing import plan_view

    display_options(still.display)
    if still.preview or still.pose is not None or still.transparent:
        raise SnapshotRefused(f"{name} is a flat board: Preview, pose and transparent output are not supported")
    if still.camera is not None:
        plan_view(still.camera, name)


def item_color(layer: str, item: dict):
    if item.get("via") in VIAS:
        return VIAS[item["via"]]
    if item.get("hole") in HOLES:
        return HOLES[item["hole"]]
    inner = re.fullmatch(r"In(\d+)\.Cu", layer)
    return INNER[(int(inner[1]) - 1) % len(INNER)] if inner else COLORS.get(layer, COLORS["Dwgs.User"])


class Held:
    """A render-service handle containing only the file path, never the parsed board."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.kind = "kicad_pcb"
        self.files: dict = {}
        self.warnings: list[str] = []

    def open(self):
        from cadgen.engine.formats import files_of
        self.files = files_of([str(self.path)])
        return {"kind": self.kind, "files": self.files, "warnings": self.warnings, "readMs": 0}

    def close(self):
        pass

    def draw(self, still: Any):
        import numpy as np
        from PIL import Image, ImageDraw
        from cadgen.engine.formats.kicad.plot import build_plot
        from cadgen.engine.render.drawing import paint_ink, plan_view
        from cadgen.engine.render.overlay import REFERENCE_HEIGHT, paint_measurements
        from cadgen.engine.render.service import finished
        from cadgen.engine.snapshot import SnapshotRefused

        started = time.perf_counter()
        refusals(still, self.path.name)
        display = display_options(still.display)
        payload = build_plot(self.path)
        sheet = payload["sheets"][0]
        layers = sheet["layers"]
        if display["layers"] is not None:
            unknown = set(display["layers"]) - {layer["id"] for layer in layers}
            if unknown:
                raise SnapshotRefused(f"unknown board layers: {', '.join(sorted(unknown))}")
        layers = [layer for layer in layers if layer["id"] in display["layers"]] if display["layers"] is not None else [
            layer for layer in layers if layer["kind"] in MODES[display["mode"]]]
        bottom = display["side"] == "bottom"
        if bottom:
            layers = list(reversed([x for x in layers if x["kind"] not in OVERLAYS])) + [x for x in layers if x["kind"] in OVERLAYS]
        # Fixed supersampling smooths native strokes; renderScale still names the requested output.
        ss = 2
        width, height = (n * ss for n in still.drawn)
        if still.camera is not None:
            cx, cy, half = plan_view(still.camera, self.path.name)
            scale = height / (2 * half)
        else:
            cx, cy = sheet["width"] / 2, -sheet["height"] / 2
            scale = min(max(width - 32 * ss, width / 2) / max(sheet["width"], 1e-9),
                        max(height - 32 * ss, height / 2) / max(sheet["height"], 1e-9))

        def place(point):
            x = sheet["width"] - point[0] if bottom else point[0]
            return ((x - cx) * scale + width / 2, (point[1] + cy) * scale + height / 2)

        image = Image.new("RGB", (width, height), "white" if display["appearance"] == "light" else "#0b0f14")
        pen = ImageDraw.Draw(image, "RGBA")
        a, b = place((0, 0)), place((sheet["width"], sheet["height"]))
        pen.rectangle((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])), fill=sheet["background"])

        def line(points, color, wide, closed=False):
            if len(points) < 2:
                return
            pts = [place(p) for p in points]
            if closed:
                pts.append(pts[0])
            wide = max(1, round(wide * scale)) if wide else ss
            pen.line(pts, fill=color, width=wide, joint="curve")
            for x, y in pts:
                r = wide / 2
                pen.ellipse((x-r, y-r, x+r, y+r), fill=color)

        for layer in layers:
            for item in layer["items"]:
                if item.get("pour") and not display["poured"]:
                    continue
                color, wide = item_color(layer["id"], item), item.get("w", 0)
                kind = item["t"]
                if kind == "poly":
                    pen.polygon([place(p) for p in item["pts"]], fill=color)
                    if wide:
                        line(item["pts"], color, wide, True)
                elif kind == "circle":
                    x, y = place(item["at"]); r = item["r"] * scale
                    pen.ellipse((x-r, y-r, x+r, y+r), fill=None if wide else color,
                                outline=color if wide else None, width=max(1, round(wide * scale)))
                elif kind == "text":
                    for stroke in item["strokes"]:
                        line(stroke, color, wide)
                else:
                    line(item["pts"], color, wide, item.get("closed", False))
        if display["mode"] == "placement":
            _placement(pen, payload["board"], place, scale, bottom, line)
        frame = np.array(image)
        if still.annotation:
            paint_ink(frame, still.annotation.get("marks", []), place, height / REFERENCE_HEIGHT)
        if still.measurements:
            paint_measurements(frame, still.measurements, lambda points: np.array([place(p) for p in points]))
        image = Image.fromarray(frame).resize(still.size, Image.Resampling.LANCZOS)
        output = io.BytesIO(); image.save(output, format="PNG")
        return output.getvalue(), {"kind": self.kind, "renderer": "pillow", "width": still.size[0], "height": still.size[1],
            "camera": "plan" if still.camera is not None else "top", "projection": "orthographic", "displayMode": display["mode"],
            "boardDisplay": display, "warnings": self.warnings, **finished(still), "timings": {"renderMs": round((time.perf_counter()-started)*1000)}}


def _placement(pen, board, place, scale, bottom, line):
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
                line([points[parents[next_pin]], points[next_pin]], (232, 238, 245, 204), 0)
            for i, point in enumerate(points):
                if i not in joined:
                    length = math.dist(point, points[next_pin])
                    if length < distance[i]:
                        distance[i], parents[i] = length, next_pin
