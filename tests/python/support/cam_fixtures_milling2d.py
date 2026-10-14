"""Fixtures for the 2.5D milling suites (contour, adaptive, slot, chamfer, engrave, helix_bore, thread_mill).

Parts are built with build123d in a temporary directory (never ``models/``):

* :func:`bracket_step`, :data:`BRACKET`: an 80 x 50 x 12 plate standing on z = 0, centred in x and y, with a Ø16
  through bore at (-25, 0), two Ø5 through tap holes (M6x1) at (25, ±15) and a stadium slot 30 long and 8 wide,
  4 deep (floor z = 8), along X centred at (2, 0).
* :func:`boss_step`, :data:`BOSS`: a 40 x 40 x 5 base with a Ø12 boss 15 tall at its centre (an M12x1.75 stud).
* :func:`counterbore_step`, :data:`COUNTERBORE`: a block with a Ø6.6 hole under a Ø11 x 6 counterbore.
* :func:`engrave_dxf`: a DXF with a line, an arc, a circle, an open polyline and a text entity (which engraving skips).

The 80 x 60 block with a stepped pocket and an island is the core's (``cam_fixtures.block_step``).
"""

from __future__ import annotations

from pathlib import Path

from tests.python.support.cam_fixtures import class_directory, mill_job, quiet  # noqa: F401 (re-exported)

BRACKET = {
    "size": (80.0, 50.0, 12.0),
    "bore": {"center": (-25.0, 0.0), "diameter": 16.0},
    "taps": {"centers": ((25.0, 15.0), (25.0, -15.0)), "diameter": 5.0},
    "slot": {"center": (2.0, 0.0), "length": 30.0, "width": 8.0, "floor_z": 8.0},
}
BOSS = {"base": (40.0, 40.0, 5.0), "diameter": 12.0, "height": 15.0}
COUNTERBORE = {"size": (40.0, 40.0, 10.0), "hole": 6.6, "counterbore": 11.0, "depth": 6.0}


def bracket_step(directory: Path, name: str = "bracket") -> Path:
    from build123d import Align, Box, Cylinder, Pos, SlotCenterToCenter, export_step, extrude

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = BRACKET["size"]
    part = Box(sx, sy, sz, align=base)
    bore = BRACKET["bore"]
    part -= Pos(*bore["center"], 0) * Cylinder(bore["diameter"] / 2, sz, align=base)
    for x, y in BRACKET["taps"]["centers"]:
        part -= Pos(x, y, 0) * Cylinder(BRACKET["taps"]["diameter"] / 2, sz, align=base)
    slot = BRACKET["slot"]
    outline = SlotCenterToCenter(slot["length"] - slot["width"], slot["width"])
    cutter = Pos(*slot["center"], slot["floor_z"]) * extrude(outline, sz - slot["floor_z"])
    part -= cutter
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def boss_step(directory: Path, name: str = "boss") -> Path:
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    bx, by, bz = BOSS["base"]
    part = Box(bx, by, bz, align=base) + Pos(0, 0, bz) * Cylinder(BOSS["diameter"] / 2, BOSS["height"], align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def counterbore_step(directory: Path, name: str = "counterbored") -> Path:
    """:data:`COUNTERBORE`: a 40 x 40 x 10 block on z = 0, centred, with a Ø6.6 through hole at its centre under a
    Ø11 counterbore 6 deep (an M6 socket-head clearance)."""
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = COUNTERBORE["size"]
    part = Box(sx, sy, sz, align=base)
    part -= Cylinder(COUNTERBORE["hole"] / 2, sz, align=base)
    part -= Pos(0, 0, sz - COUNTERBORE["depth"]) * Cylinder(COUNTERBORE["counterbore"] / 2, COUNTERBORE["depth"],
                                                            align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def engrave_dxf(directory: Path, name: str = "mark") -> Path:
    import ezdxf

    document = ezdxf.new()
    document.header["$INSUNITS"] = 4
    space = document.modelspace()
    space.add_line((-30, -15), (-10, -15))
    space.add_arc((0, -15), radius=5, start_angle=0, end_angle=180)
    space.add_circle((20, 10), radius=4)
    space.add_lwpolyline([(-30, 5), (-25, 15), (-20, 5)])
    space.add_text("HI", dxfattribs={"height": 5, "insert": (0, 5)})
    path = directory / f"{name}.dxf"
    document.saveas(path)
    return path


def tools(**extra) -> list[dict]:
    """T1 6 mm flat (flutes 15), T2 4 mm flat, T3 90° vee 10 mm, T4 M6x1 thread mill Ø4.8, T5 M12x1.75 thread mill
    Ø8, T6 30° engraver 3 mm, then any ``extra`` tools."""
    out = [
        {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 15, "stickout_mm": 30},
        {"id": "T2", "type": "flat", "diameter_mm": 4, "flutes": 3, "flute_length_mm": 14, "stickout_mm": 25},
        {"id": "T3", "type": "vee", "diameter_mm": 10, "angle_deg": 90, "flute_length_mm": 6, "stickout_mm": 25},
        {"id": "T4", "type": "thread_mill", "diameter_mm": 4.8, "pitch_mm": 1.0, "flute_length_mm": 14,
         "stickout_mm": 25},
        {"id": "T5", "type": "thread_mill", "diameter_mm": 8, "pitch_mm": 1.75, "flute_length_mm": 18,
         "stickout_mm": 30},
        {"id": "T6", "type": "engraver", "diameter_mm": 3, "angle_deg": 30, "tip_diameter_mm": 0.1,
         "flute_length_mm": 6, "stickout_mm": 20},
    ]
    out.extend(extra.values())
    return out


def job(operations: list[dict], **kwargs) -> dict:
    """A GRBL mill job on the 2.5D tool set (:func:`tools`)."""
    kwargs.setdefault("tools", tools())
    return mill_job(operations, **kwargs)


def plan_error(ops, index: int = 0):
    """``(kind, message)`` of the plan error operation ``index`` (an op plan list from ``plan_setups``) was refused
    with, else None: a planner's ``PlanError`` becomes the op's ``meta["plan_error"]``, and every other op still
    plans."""
    found = next(op for op in ops if op.index == index).meta.get("plan_error")
    return None if found is None else (found["kind"], found["message"])


def face_at(features, *, surface: str, **match) -> str:
    """The first face of a features() result with ``surface`` and every ``match`` (``z_mm``, ``diameter_mm``,
    ``hole``), compared within 1e-3."""
    for face in features.faces:
        if face["surface"] != surface:
            continue
        if all(abs(face.get(key, float("nan")) - value) < 1e-3 if isinstance(value, float)
               else face.get(key) == value for key, value in match.items()):
            return face["ref"]
    raise LookupError(f"no {surface} face with {match}")
