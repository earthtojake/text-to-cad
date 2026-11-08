"""Native schematic stills: read the saved sheets on each draw, rasterize one page of their plot, discard it.

No XCAF document, model worker, browser or KiCad process is involved. The page is the schematic plot's
(:mod:`cad.engine.formats.kicad.schematic_plot`): each sheet instance one page of layers, painted with
Pillow in KiCad's default schematic colours (its light theme, as every snapshot is), text in the
board's stroke font. The Display is ``{sheet, border}``: the sheet's path (``/`` the root,
``/Power/``) and whether the page's edge is drawn (off unless asked).
Without a camera the picture frames what the page draws (the whole page with its border on); a plan
camera frames its window, as a board's does.
"""
from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

DISPLAY_KEYS = {"sheet", "border"}
#: KiCad's default schematic colours (its light theme), by layer kind and by what an item is.
LIGHT = {
    "background": "#F5F4EF", "sheet": "#840000", "notes": "#0000C2", "sheet_box": "#840000", "sheet_name": "#006464",
    "sheet_file": "#725600", "sheet_pin": "#006464", "sheet_field": "#840084", "symbol": "#840000",
    "symbol_background": "#FFFFC2", "pin": "#840000", "wire": "#009600", "bus": "#000084", "junction": "#009600",
    "no_connect": "#000084", "pin_number": "#A90000", "pin_name": "#006464", "reference": "#006464",
    "value": "#006464", "field": "#840084", "local": "#0F0F0F", "global": "#840000", "hierarchical": "#725600",
}


def display_options(value: Any, grid: bool = False) -> dict:
    """A schematic's ``--display``: ``{sheet, border}`` (JSON, or a JSON file of it)."""
    from cad.engine.snapshot import SnapshotRefused, _json_or_file

    if isinstance(value, str):
        text = value.strip()
        value = _json_or_file(text, "--display") if text else None
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - DISPLAY_KEYS or grid:
        raise SnapshotRefused(f"a schematic's display takes {', '.join(sorted(DISPLAY_KEYS))}: "
                              "{\"sheet\": \"/Power/\", \"border\": true}")
    display = {"sheet": "/", "border": False, **value}
    if not isinstance(display["sheet"], str) or not display["sheet"]:
        raise SnapshotRefused("a schematic's display.sheet is a sheet's path: / (the root), /Power/")
    if type(display["border"]) is not bool:
        raise SnapshotRefused("a schematic's display.border is true or false")
    parts = [part for part in display["sheet"].split("/") if part]
    display["sheet"] = "/" + "".join(f"{part}/" for part in parts)
    return display


def refusals(still: Any, name: str) -> None:
    from cad.engine.render.drawing import plan_view
    from cad.engine.snapshot import SnapshotRefused

    display_options(still.display)
    if still.preview or still.pose is not None or still.transparent:
        raise SnapshotRefused(f"{name} is a flat schematic: Preview, pose and transparent output are not supported")
    if still.view is not None:
        raise SnapshotRefused(f"{name} is a flat schematic: --view is a part's named view, and a schematic has none")
    if still.references:
        raise SnapshotRefused(f"{name} is a schematic: lighting references is a board's for now")
    if still.camera is not None:
        plan_view(still.camera, name)


def _rgba(color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), round(255 * max(0.0, min(1.0, opacity)))


def item_color(kind: str, item: dict, theme: dict) -> str:
    """The colour an item of a layer of ``kind`` is drawn in: its own where the file gives one, else
    the theme's for what it is (a field's name, a label's kind, a sheet's role), else its layer's."""
    if item.get("color"):
        return item["color"]
    if kind == "field":
        field = item.get("field")
        return theme["reference"] if field == "Reference" else theme["value"] if field == "Value" else theme["field"]
    if kind == "label":
        return theme.get(item.get("label"), theme["local"])
    if kind == "sheet_box" and item.get("role"):
        return theme.get(f"sheet_{item['role']}", theme["sheet_box"])
    return theme.get(kind, theme["symbol"])


def extent(layers: list[dict], border: bool, page: list[float]) -> tuple[float, float, float, float]:
    """The box of what a page draws (the page itself with its border on), mm."""
    if border:
        return page[0], page[1], page[0] + page[2], page[1] + page[3]
    xs: list[float] = []
    ys: list[float] = []
    for layer in layers:
        if layer["kind"] == "sheet":
            continue
        for item in layer["items"]:
            if item["t"] == "circle":
                xs += [item["at"][0] - item["r"], item["at"][0] + item["r"]]
                ys += [item["at"][1] - item["r"], item["at"][1] + item["r"]]
                continue
            for stroke in item.get("strokes") or [item.get("pts") or []]:
                xs += [point[0] for point in stroke]
                ys += [point[1] for point in stroke]
    if not xs:
        return page[0], page[1], page[0] + page[2], page[1] + page[3]
    return min(xs), min(ys), max(xs), max(ys)


class _Painter:
    """A page of layers on a Pillow image, in millimetres placed by ``place``."""

    def __init__(self, image, place, scale: float, ss: int):
        from PIL import ImageDraw

        self.pen = ImageDraw.Draw(image, "RGBA")
        self.place, self.scale, self.ss = place, scale, ss

    def _width(self, wide: float) -> int:
        return max(self.ss, round(wide * self.scale)) if wide > 0 else self.ss

    def line(self, points, fill, wide: float) -> None:
        if len(points) < 2:
            return
        pts = [self.place(p) for p in points]
        width = self._width(wide)
        self.pen.line(pts, fill=fill, width=width, joint="curve")
        if width > 2:
            r = width / 2
            for x, y in (pts[0], pts[-1]):
                self.pen.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    def item(self, kind: str, item: dict, theme: dict) -> None:
        color = item_color(kind, item, theme)
        fill = _rgba(color, item.get("opacity", 1.0))
        t = item["t"]
        if t == "poly":
            paint = _rgba(theme["symbol_background"]) if item.get("fill") == "background" else fill
            self.pen.polygon([self.place(p) for p in item["pts"]], fill=paint)
        elif t == "path":
            points = item["pts"]
            if item.get("pairs"):
                for a, b in zip(points[0::2], points[1::2]):
                    self.line([a, b], fill, item.get("w", 0))
            else:
                self.line(points, fill, item.get("w", 0))
        elif t == "circle":
            x, y = self.place(item["at"])
            r = item["r"] * self.scale
            if item.get("w", 0) > 0:
                self.pen.ellipse((x - r, y - r, x + r, y + r), outline=fill, width=self._width(item["w"]))
            else:
                self.pen.ellipse((x - r, y - r, x + r, y + r), fill=fill)
        elif t == "text":
            for stroke in item["strokes"]:
                self.line(stroke, fill, item.get("w", 0))


def page_of(payload: dict, sheet: str) -> dict:
    from cad.engine.snapshot import SnapshotRefused

    for page in payload["sheets"]:
        if page["path"] == sheet:
            return page
    known = ", ".join(page["path"] for page in payload["sheets"])
    raise SnapshotRefused(f"the schematic has no sheet {sheet}; its sheets are {known}")


def draw_page(path: Path, still: Any) -> tuple[bytes, dict[str, Any]]:
    """One page of the schematic at ``path`` as PNG bytes, and what was drawn (a snapshot's report)."""
    import numpy as np
    from PIL import Image

    from cad.engine.formats.kicad.schematic_plot import build_schematic_plot
    from cad.engine.render.drawing import paint_ink, plan_view
    from cad.engine.render.overlay import REFERENCE_HEIGHT, paint_measurements
    from cad.engine.render.service import finished
    from cad.engine.snapshot import SnapshotRefused

    started = time.perf_counter()
    display = display_options(still.display)
    try:
        payload = build_schematic_plot(path, sheets=[display["sheet"]], index=False)
    except ValueError as error:
        raise SnapshotRefused(str(error)) from None
    page = page_of(payload, display["sheet"])
    theme = LIGHT
    layers = [layer for layer in page["layers"] if display["border"] or layer["kind"] != "sheet"]
    ss = 2
    width, height = (n * ss for n in still.drawn)
    if still.camera is not None:
        cx, cy, half = plan_view(still.camera, path.name)
        scale = height / (2 * half)
    else:
        x0, y0, x1, y1 = extent(layers, display["border"], page["page"])
        pad = 0.04
        span_x, span_y = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        scale = min(width * (1 - 2 * pad) / span_x, height * (1 - 2 * pad) / span_y)
        cx, cy = (x0 + x1) / 2, -(y0 + y1) / 2

    def place(point):
        return (point[0] - cx) * scale + width / 2, (point[1] + cy) * scale + height / 2

    image = Image.new("RGB", (width, height), theme["background"])
    painter = _Painter(image, place, scale, ss)
    for layer in layers:
        for item in layer["items"]:
            if item["t"] == "poly":
                painter.item(layer["kind"], item, theme)
        for item in layer["items"]:
            if item["t"] != "poly":
                painter.item(layer["kind"], item, theme)
    frame = np.array(image)
    if still.annotation:
        paint_ink(frame, still.annotation.get("marks", []), place, height / REFERENCE_HEIGHT)
    if still.measurements:
        paint_measurements(frame, still.measurements, lambda points: np.array([place(p) for p in points]))
    image = Image.fromarray(frame).resize(still.size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), {
        "kind": "kicad_sch", "renderer": "pillow", "width": still.size[0], "height": still.size[1],
        "camera": "plan" if still.camera is not None else "page", "projection": "orthographic", "displayMode": "schematic",
        "preview": False, "schematicDisplay": display, "sheet": page["path"], "page": page["number"],
        "warnings": list(payload.get("warnings") or []), **finished(still),
        "timings": {"renderMs": round((time.perf_counter() - started) * 1000)}}


class Held:
    """A render-service handle holding only the schematic's path, never its parsed sheets; the files it
    watches are every sheet file of its hierarchy, so an edit to any sheet draws anew."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.kind = "kicad_sch"
        self.files: dict = {}
        self.warnings: list[str] = []

    def open(self):
        from cad.engine.formats import files_of
        from cad.engine.formats.kicad.schematic import read_schematic_index

        index, _warnings = read_schematic_index(self.path)
        self.files = files_of(sorted({str(self.path), *(str(sheet.file) for sheet in index.sheets if sheet.file.is_file())}))
        return {"kind": self.kind, "files": self.files, "warnings": self.warnings, "readMs": 0}

    def close(self):
        pass

    def draw(self, still: Any):
        refusals(still, self.path.name)
        return draw_page(self.path, still)
