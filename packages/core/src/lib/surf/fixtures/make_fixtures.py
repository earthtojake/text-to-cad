"""Regenerate the surf/mesh test fixtures in this directory.

Each fixture is one component as cadgen stores it: ``<name>.surf`` (its SURF:
exact surfaces and the topology index) and ``<name>.l<level>.glb`` (cadgen's
OCCT mesh of it at that viewer LOD level, ``lodPolicy.js``), bound to each
other by the SURF's digest and to a fixed test surface input
(``sha256("cadgen-test-fixture:<name>")``, recorded in ``fixtures.json``).
``<name>.selectors.json`` is the component's selector table as cadgen stores
it beside the SURF (``cadgen._internal.selector_table``): what the page joins
to the mesh, and the oracle every id and fact a JS test expects comes from.

The shapes are built here, not read from ``models/``. Run from the repository
root with the repo's Python whenever cadgen's SURF or mesh output changes:

    .venv/bin/python packages/core/src/lib/surf/fixtures/make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
from math import cos, sin, tau
from pathlib import Path

from build123d import (
    Align, Axis, Box, BuildLine, BuildPart, BuildSketch, Circle, Color, Cylinder, Line, Location, Locations,
    Mode, Plane, Polygon, Pos, Rectangle, SlotOverall, Spline, extrude, fillet, loft, make_face, revolve,
)

HERE = Path(__file__).resolve().parent
# lodPolicy.js LOD_TESSELLATION_LEVELS (the coarse and default rungs).
LEVELS = {0: (2e-3, 1.4), 1: (1.5e-3, 0.35)}


def sun_gear():
    """The planetary assembly's 24-tooth sun gear: straight-sided teeth and a bore."""
    teeth, root, tip, pitch = 24, 21.0, 27.0, tau / 24
    points = []
    for tooth in range(teeth):
        center = -pitch / 2 + tooth * pitch
        for radius, span in ((root, -0.42), (tip, -0.18), (tip, 0.18), (root, 0.42)):
            angle = center + span * pitch / 2
            points.append((radius * cos(angle), radius * sin(angle)))
    with BuildPart() as gear:
        with BuildSketch(Plane.XY):
            Polygon(points, align=None)
        extrude(amount=8.0)
        with Locations(Location((0, 0, -0.5))):
            Cylinder(5.0, 9.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    part = gear.part
    part.color = Color(0.98, 0.62, 0.18, 1.0)
    return part


def cam_follower_roller():
    """A roller with a bearing bore and rounded outer profile: cylinders, planes and tori."""
    with BuildPart() as roller:
        Cylinder(16.0, 18.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0, 0, -1))):
            Cylinder(6.0, 20.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    part = fillet(roller.part.edges().filter_by(lambda edge: edge.geom_type.name == "CIRCLE"), 1.8)
    part.color = Color(0.60, 0.64, 0.67, 1.0)
    return part


def mixed():
    """Planes, cylinders, a torus, a surface of revolution and NURBS in one solid."""
    base = Box(40, 24, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
    boss = Pos(-10, 0, 6) * Cylinder(6, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = base + boss
    body = fillet(body.edges().filter_by(lambda edge: edge.geom_type.name == "CIRCLE").sort_by(Axis.Z)[-1], 1.5)
    with BuildPart() as knob:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline((0, 6), (3, 7.5), (4, 10), (2.5, 13), (0, 13.5))
                Line((0, 13.5), (0, 6))
            make_face()
        revolve(axis=Axis.Z)
    lofted = loft([Plane.XY.offset(6) * Pos(10, 0) * Rectangle(10, 10), Plane.XY.offset(14) * Pos(10, 0) * Circle(3)])
    part = body + Pos(10, 0, 0) * knob.part.moved(Location((-10, 0, 0))) + lofted
    part.color = Color(0.35, 0.55, 0.85, 1.0)
    return part


def slot():
    """An extruded slot: two lines and two half-circles chain round each cap, and the
    rounded walls join the flat ones in one tangent group."""
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            SlotOverall(30, 10)
        extrude(amount=5)
    solid = part.part
    solid.color = Color(0.72, 0.30, 0.30, 1.0)
    return solid


def main() -> None:
    from cadgen._internal import occt_mesh
    from cadgen._internal.component_package import decode_display_shape, prepare_geometry_component
    from cadgen._internal.selector_table import build_selector_table, selector_table_bytes
    from cadgen._internal.surface_extract import extract_surface_component, read_surf

    manifest = {}
    for name, build, levels in (("sun_gear", sun_gear, (0, 1)), ("cam_follower_roller", cam_follower_roller, (0, 1)),
                                ("mixed", mixed, (0, 1)), ("slot", slot, (0, 1))):
        prepared = prepare_geometry_component(build())
        entry, payload = prepared["entry"], prepared["payload"]
        shape = decode_display_shape(entry, payload)
        surf = extract_surface_component(shape.wrapped, face_colors=getattr(shape, "cad_face_ordinal_colors", None))
        index, _floats = read_surf(surf)
        table = selector_table_bytes(build_selector_table(shape.wrapped, index))
        (HERE / f"{name}.selectors.json").write_bytes(table + b"\n")
        surface_input = hashlib.sha256(f"cadgen-test-fixture:{name}".encode()).hexdigest()
        surface_object = hashlib.sha256(surf).hexdigest()
        (HERE / f"{name}.surf").write_bytes(surf)
        meshes = {}
        for level in levels:
            chord, angle = LEVELS[level]
            body = occt_mesh.mesh_component(decode_display_shape(entry, payload).wrapped, index,
                                            surface_input=surface_input, surface_object=surface_object,
                                            chord=chord, angle=angle)
            (HERE / f"{name}.l{level}.glb").write_bytes(body)
            meshes[str(level)] = {"chordTolerance": chord, "angleTolerance": angle, "byteLength": len(body)}
        manifest[name] = {"surfaceInput": surface_input, "surfaceObject": surface_object,
                          "faces": len(index["faces"]), "edges": len(index["edges"]),
                          "selectorsByteLength": len(table), "meshes": meshes}
    (HERE / "fixtures.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
