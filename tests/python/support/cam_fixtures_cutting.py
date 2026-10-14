"""Fixtures for the cutting and wire EDM suites (``test_cam_cutting_*.py``): a DXF bracket, STEP plates, jobs.

The bracket (:func:`bracket_dxf`, :data:`BRACKET`) is an L-shaped plate 80 x 50 mm (legs 20 and 30 mm wide, one
inside corner at (30, 20)) with three Ø6 holes, an 8 mm square hole and a 15 x 6 mm slot drawn as loose lines and
arcs (so the reader has to join them), and beside it a separate washer Ø20 with a Ø8 hole: two parts, five holes.
Written with ezdxf in mm. The plate (:func:`plate_step`) is 60 x 40 x 5 with four Ø8 holes and a 20 x 8 mm slot;
:func:`pocketed_plate_step` adds a blind pocket, which a sheet cut must refuse.
"""

from __future__ import annotations

import math
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

BRACKET = {
    "outline": ((0.0, 0.0), (80.0, 0.0), (80.0, 20.0), (30.0, 20.0), (30.0, 50.0), (0.0, 50.0)),
    "round_holes": (((10.0, 10.0), 6.0), ((70.0, 10.0), 6.0), ((15.0, 42.0), 6.0)),
    "square_hole": {"center": (15.0, 30.0), "size": 8.0},
    "slot": {"from": (45.0, 10.0), "to": (60.0, 10.0), "width": 6.0},
    "washer": {"center": (105.0, 25.0), "diameter": 20.0, "hole": 8.0},
}
PLATE = {"size": (60.0, 40.0, 5.0), "holes": ((-22.0, -12.0), (22.0, -12.0), (-22.0, 12.0), (22.0, 12.0)),
         "hole_diameter": 8.0, "slot": {"center": (0.0, 0.0), "length": 20.0, "width": 8.0}}


def bracket_area() -> float:
    """The bracket's and the washer's material area (mm²), for kerf checks."""
    outline = 80.0 * 20.0 + 30.0 * 30.0
    holes = sum(math.pi * (d / 2) ** 2 for _, d in BRACKET["round_holes"]) + BRACKET["square_hole"]["size"] ** 2
    slot = BRACKET["slot"]
    holes += (slot["to"][0] - slot["from"][0]) * slot["width"] + math.pi * (slot["width"] / 2) ** 2
    washer = BRACKET["washer"]
    return outline - holes + math.pi * ((washer["diameter"] / 2) ** 2 - (washer["hole"] / 2) ** 2)


def bracket_dxf(directory: Path, name: str = "bracket") -> Path:
    import ezdxf

    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    space = document.modelspace()
    space.add_lwpolyline(BRACKET["outline"], close=True)
    for centre, diameter in BRACKET["round_holes"]:
        space.add_circle(centre, diameter / 2)
    cx, cy = BRACKET["square_hole"]["center"]
    h = BRACKET["square_hole"]["size"] / 2
    space.add_lwpolyline([(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)], close=True)
    slot = BRACKET["slot"]
    (x0, y), (x1, _) = slot["from"], slot["to"]
    r = slot["width"] / 2
    space.add_line((x0, y - r), (x1, y - r))
    space.add_line((x1, y + r), (x0, y + r))
    space.add_arc((x1, y), r, -90, 90)
    space.add_arc((x0, y), r, 90, 270)
    washer = BRACKET["washer"]
    space.add_circle(washer["center"], washer["diameter"] / 2)
    space.add_circle(washer["center"], washer["hole"] / 2)
    path = directory / f"{name}.dxf"
    document.saveas(path)
    return path


def plate_step(directory: Path, name: str = "plate") -> Path:
    from build123d import Align, Box, Cylinder, Pos, SlotOverall, extrude, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = PLATE["size"]
    part = Box(sx, sy, sz, align=base)
    for x, y in PLATE["holes"]:
        part -= Pos(x, y, 0) * Cylinder(PLATE["hole_diameter"] / 2, sz, align=base)
    slot = PLATE["slot"]
    part -= extrude(SlotOverall(slot["length"], slot["width"]), sz)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def pocketed_plate_step(directory: Path, name: str = "pocketed") -> Path:
    from build123d import Align, Box, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = PLATE["size"]
    part = Box(sx, sy, sz, align=base) - Pos(0, 0, sz - 2) * Box(20, 10, 2, align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


_POSTS = {"router": "grbl", "laser": "grbl", "plasma": "plasma", "waterjet": "waterjet", "wire_edm": "wire_edm",
          "mill": "grbl"}


def cut_job(kind: str, operation: dict | None = None, *, thickness: float = 3.0, material: str = "steel-1018",
            tool: dict | None = None, machine: dict | None = None, margin: float = 5.0) -> dict:
    """One sheet-cut job: a laser, plasma or waterjet with a beam (T1), a router with a 6 mm flat (T1), or a wire EDM
    with a 0.25 mm wire (T1)."""
    tools = {"router": {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 2, "flute_length_mm": 22,
                        "stickout_mm": 30},
             "wire_edm": {"id": "T1", "type": "wire", "diameter_mm": 0.25},
             "laser": {"id": "T1", "type": "beam", "kerf_mm": 0.2},
             "plasma": {"id": "T1", "type": "beam", "kerf_mm": 1.5},
             "waterjet": {"id": "T1", "type": "beam", "kerf_mm": 0.9}}
    op = {"op": "wire_edm" if kind == "wire_edm" else "cut", "tool": "T1", **(operation or {})}
    # A job names its post (never guessed): the fixture's is the usual one for the kind.
    machine = dict(machine or {"kind": kind})
    machine.setdefault("post", _POSTS[machine.get("kind", kind)])
    return {
        "machine": machine,
        "material": material,
        "stock": {"kind": "sheet", "thickness_mm": thickness, "margin_mm": margin},
        "tools": [tool or tools[kind]],
        "setups": [{"id": "sheet", "orientation": "+Z", "origin": "stock-top-corner", "operations": [op]}],
    }
