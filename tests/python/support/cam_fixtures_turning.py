"""Turning fixtures for the B5 suites (``tests/python/packages/cadgen/cam/test_cam_turning_*.py``).

The shaft (:func:`shaft_step`, :data:`SHAFT`) is a body of revolution about Z, front face at z = 60, back at z = 0,
built by revolving its half-section (radius, z) with build123d in a temporary directory, never ``models/``:

====================  ===============================================================================================
z 60 -> 44            Ø20 thread major diameter (M20x1.5), a 1 x 45° chamfer at the front edge
z 44 -> 41            a 3 mm thread relief groove, Ø17
z 41 -> 20            Ø30, a 1 x 45° chamfer at its front shoulder, a 4 mm groove Ø26 at z 28 -> 32
z 20 -> 0             Ø36
bore                  Ø10 from the front face, 15 mm deep (flat bottom at z 45)
====================  ===============================================================================================

``cross_hole=True`` adds a Ø4 hole across the Ø30 section at z 36 (an off-axis feature a lathe leaves);
``along_x=True`` lies the shaft along X. :func:`block_step` is a box, which is not a body of revolution.
:func:`lathe_job` builds the job dict the suites plan; :func:`face_ref` finds a cylinder by its diameter.
"""

from __future__ import annotations

from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

#: The shaft's numbers, for assertions (radii and z in part mm).
SHAFT = {
    "front_z": 60.0, "back_z": 0.0,
    "thread": {"major_r": 10.0, "z": (44.0, 60.0), "pitch": 1.5},
    "relief": {"r": 8.5, "z": (41.0, 44.0)},
    "middle": {"r": 15.0, "z": (20.0, 41.0)},
    "groove": {"r": 13.0, "z": (28.0, 32.0)},
    "back": {"r": 18.0, "z": (0.0, 20.0)},
    "bore": {"r": 5.0, "z": (45.0, 60.0)},
    "chamfer": 1.0,
}

#: The half-section, (radius, z), counter-clockwise from the axis at the back.
SECTION = (
    (0.0, 0.0), (18.0, 0.0), (18.0, 20.0), (15.0, 20.0), (15.0, 28.0), (13.0, 28.0), (13.0, 32.0), (15.0, 32.0),
    (15.0, 40.0), (14.0, 41.0), (8.5, 41.0), (8.5, 44.0), (10.0, 44.0), (10.0, 59.0), (9.0, 60.0), (5.0, 60.0),
    (5.0, 45.0), (0.0, 45.0),
)


#: A bushing: Ø30 outside, a Ø16 bore 10 deep (an inside thread's minor diameter), a 3 mm inside groove Ø19 behind
#: it, then Ø14 to z 30 and Ø12 through: (radius, z) half-section.
BUSH = ((6.0, 0.0), (15.0, 0.0), (15.0, 60.0), (8.0, 60.0), (8.0, 50.0), (9.5, 50.0), (9.5, 47.0), (7.0, 47.0),
        (7.0, 30.0), (6.0, 30.0))


def revolved_step(directory: Path, section, name: str, *, cross_hole: bool = False, along_x: bool = False) -> Path:
    from build123d import Axis, BuildLine, BuildPart, BuildSketch, Cylinder, Locations, Mode, Plane, Polyline, Pos, \
        export_step, make_face, revolve

    with BuildPart() as built:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*section, close=True)
            make_face()
        revolve(axis=Axis.Z)
        if cross_hole:
            with Locations(Pos(0, 0, 36)):
                Cylinder(2.0, 40.0, rotation=(0, 90, 0), mode=Mode.SUBTRACT)
    part = built.part.rotate(Axis.Y, 90) if along_x else built.part
    path = Path(directory) / f"{name}.step"
    export_step(part, str(path))
    return path


def shaft_step(directory: Path, name: str = "shaft", *, cross_hole: bool = False, along_x: bool = False) -> Path:
    """The shaft; ``along_x`` lies it along the part's X (front at x = 60)."""
    return revolved_step(directory, SECTION, name, cross_hole=cross_hole, along_x=along_x)


def bush_step(directory: Path, name: str = "bush") -> Path:
    return revolved_step(directory, BUSH, name)


def block_step(directory: Path, name: str = "block") -> Path:
    from build123d import Align, Box, export_step

    path = Path(directory) / f"{name}.step"
    export_step(Box(30, 20, 40, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(path))
    return path


def lathe_job(operations: list[dict], *, tools: list[dict] | None = None, stock: dict | None = None,
              machine: dict | None = None, material: str = "aluminum-6061", setups: list[dict] | None = None) -> dict:
    """A lathe job on a Ø40 x 75 bar (1 mm face stock) with an 80° C-insert turning tool (T1, R0.4), a 35° V-insert
    finisher (T2, R0.2), a 3 mm grooving tool (T3), a 1.5 mm pitch threading tool (T4), a 3 mm part-off blade (T5), an
    8 mm drill (T6), a boring bar (T7, R0.2, 6 mm bar) and a 2 mm grooving tool (T8)."""
    return {
        "machine": machine or {"kind": "lathe", "post": "linuxcnc", "max_rpm": 4000, "travel_mm": [200, 300]},
        "material": material,
        "stock": stock or {"kind": "cylinder", "diameter_mm": 40, "length_mm": 75, "face_stock_mm": 1.0},
        "tools": tools or [
            {"id": "T1", "type": "turn", "insert": "C", "nose_radius_mm": 0.4},
            {"id": "T2", "type": "turn", "insert": "V", "nose_radius_mm": 0.2},
            {"id": "T3", "type": "groove", "width_mm": 3},
            {"id": "T4", "type": "thread", "pitch_mm": 1.5},
            {"id": "T5", "type": "partoff", "width_mm": 3},
            {"id": "T6", "type": "drill", "diameter_mm": 8},
            {"id": "T7", "type": "turn", "insert": "D", "nose_radius_mm": 0.2, "diameter_mm": 6},
            {"id": "T8", "type": "groove", "width_mm": 2},
        ],
        "setups": setups or [{"id": "turn", "orientation": "+Z", "origin": "stock-top-center",
                              "operations": operations}],
    }


def face_ref(features, diameter: float, *, hole: bool = False) -> str:
    """The ref of the cylinder of ``diameter`` (a ``cam features`` result), a bore when ``hole``."""
    for face in features.faces:
        if face.get("surface") == "cylinder" and abs(face.get("diameter_mm", 0) - diameter) < 1e-6 \
                and bool(face.get("hole")) == hole:
            return face["ref"]
    raise LookupError(f"no {'bore' if hole else 'cylinder'} Ø{diameter:g}")
