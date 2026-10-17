"""Regenerate the part fixtures in this directory.

Each fixture is one component's part as cadgen stores it: ``<name>.glb`` (cadgen's
mesh of it at the display tolerance), naming a fixed test part key
(``sha256("cadgen-test-fixture:<name>")`` at this cadgen's part version, recorded in
``fixtures.json``), and ``<name>.selectors.json``, the component's selector table
(``cadgen._internal.selector_table``): what the page joins to the mesh, and the
oracle every id and fact a JS test expects comes from. Both are made as cadgen
derives a part (``cadgen.store.parts``): the mesh from the component's topology
facts, extracted in memory, and its face colours, and the table from the facts,
its elements' names and the mesh's boxes. Each shape is built inside a kernel run, as a
model's build makes it, so its elements are named by their lineage
(``f:sun_gear.extrude1.3``), as a build names them.

The shapes are built here, not read from ``models/``. Run from the repository
root with the repo's Python whenever cadgen's selector table, its names or its
mesh output changes:

    .venv/bin/python packages/core/src/lib/parts/fixtures/make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
from math import cos, sin, tau
from pathlib import Path

from build123d import (
    Align, BuildPart, BuildSketch, Cylinder, Location, Locations, Mode, Plane, Polygon, SlotOverall, extrude, fillet,
)

HERE = Path(__file__).resolve().parent


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
    return gear.part


def cam_follower_roller():
    """A roller with a bearing bore and rounded outer profile: cylinders, planes and tori."""
    with BuildPart() as roller:
        Cylinder(16.0, 18.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0, 0, -1))):
            Cylinder(6.0, 20.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    return fillet(roller.part.edges().filter_by(lambda edge: edge.geom_type.name == "CIRCLE"), 1.8)


def slot():
    """An extruded slot: two lines and two half-circles chain round each cap, and the
    rounded walls join the flat ones in one tangent group."""
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            SlotOverall(30, 10)
        extrude(amount=5)
    return part.part


def main() -> None:
    from cadgen._internal import kernel_memo, tessellate
    from cadgen._internal.component_package import decode_display_shape, effective_face_colors, prepare_geometry_component
    from cadgen._internal.geometric_tokens import element_names
    from cadgen._internal.selector_table import build_selector_table, selector_table_bytes
    from cadgen._internal.topology_extract import extract_topology_facts
    from cadgen.store.index import versioned_key
    from cadgen.store.parts import PART_VERSION
    from cadgen.tessellation_policy import DISPLAY_TESSELLATION

    chord, angle = DISPLAY_TESSELLATION["chordTolerance"], DISPLAY_TESSELLATION["angleTolerance"]
    manifest = {}
    for name, build in (("sun_gear", sun_gear), ("cam_follower_roller", cam_follower_roller), ("slot", slot)):
        with kernel_memo.run(Path(__file__)) as run:
            shape = build()
        _construction, lineage = run.identify(shape)
        prepared = prepare_geometry_component(shape)
        entry, payload = prepared["entry"], prepared["payload"]
        topods = decode_display_shape(entry, payload).wrapped
        colors = effective_face_colors(topods, entry["faceColors"])
        facts = extract_topology_facts(topods)
        part = versioned_key(hashlib.sha256(f"cadgen-test-fixture:{name}".encode()).hexdigest(), PART_VERSION)
        meshed = tessellate.mesh_component(topods, facts, colors, part=part, chord=chord, angle=angle)
        table = build_selector_table(topods, facts, element_names(lineage, topods), boxes=meshed.boxes)
        (HERE / f"{name}.selectors.json").write_bytes(selector_table_bytes(table) + b"\n")
        (HERE / f"{name}.glb").write_bytes(meshed.body)
        manifest[name] = {"part": part}
    (HERE / "fixtures.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
