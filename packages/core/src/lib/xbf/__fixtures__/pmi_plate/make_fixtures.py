"""Write the PMI tests' plate fixtures: an engine document as ``cadgen serve`` answers it (its
structure and its part buffer), built in four versions of one model, in one folder, as a person's
edits are:

* ``v1``: a 100 x 60 x 10 mm plate with a 10 mm hole, its PMI naming its faces by the engine's
  element names -- datum A on the bottom, the thickness, the hole's diameter, its position to A,
  the top's flatness, and basic distances from the front and the left side to the hole's axis;
* ``v2``: 12 mm thick with a 12 mm hole, every name kept: the same annotations, measured anew;
* ``v3``: a square cut where the hole was: the hole's name now on a flat face, where a diameter and
  a position cannot stand; the basics to it measure to that face (a build is of itself alone: none
  says what the face was before);
* ``v4``: the v1 plate as a model-based definition -- the thickness given limits, a surface profile
  on the hole, a general profile 0.5 to A (Note 1, on every face nothing else controls), a general
  note and a flag note on the hole and its diameter, their texts the project's notes, and two views: a
  section "A-A" (front, cut across y through the hole's axis, keeping the far side so the front
  camera sees the cut) placing the diameter its own way, and an iso view showing everything.

Tolerance values and note texts are illustrative: a project's words, never cadgen's.
``constructions.json`` beside them is the layout the viewer makes of them (``xbfPmiLayout.test.js``);
write it again after these change. Regenerate, from the repository root:

    .venv/bin/python packages/core/src/lib/xbf/__fixtures__/pmi_plate/make_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from cadgen.engine import build as engine_build
from cadgen.engine.serve import Server

HERE = Path(__file__).resolve().parent

# The model, named for the element names its PMI is written in (``f:edit_plate.body_make_box1.5``).
MODEL = '''from __future__ import annotations

# A plate whose PMI names its faces by the engine's element names, built in four versions: as
# made, thicker with a bigger hole (every name kept), with a square cut in place of the hole (the
# hole's name gone), and as made again, a model-based definition (limits, profiles, notes, views),
# the hole located by basic distances from two sides. Tolerance values and note texts are
# illustrative.
import build123d as bd

from cadgen import xbf
from cadgen.ap242 import (annotate, datum, dimensional_location, dimensional_size, flatness_tolerance, general_profile,
                          limits, note, place, plus_minus_tolerance, position_tolerance, section,
                          surface_profile_tolerance, view)

THICKNESS = {thickness}
HOLE = "{hole}"
RADIUS = {radius}
TOP, BOTTOM = "f:edit_plate.body_make_box1.6;M:edit_plate.body", "f:edit_plate.body_make_box1.5;M:edit_plate.body"
FRONT, LEFT = "f:edit_plate.body_make_box1.3", "f:edit_plate.body_make_box1.1"
HOLE_FACE = "f:edit_plate.cut.1;M:edit_plate.body"
# The project's notes by name, as a module of its own code would hold them (here inline).
NOTES = {{"edges": "Break all sharp edges 0.2 max", "primer-mask": "Mask these features before coating with primer"}}


@xbf(out="edit_plate.xbf")
def edit_plate():
    cut = bd.Cylinder(RADIUS, THICKNESS) if HOLE == "round" else bd.Box(2 * RADIUS, 2 * RADIUS, THICKNESS)
    body = bd.Box(100, 60, THICKNESS) - cut
    body.label = "plate"
    return annotate(
        body,
        datum("A", BOTTOM, presentation=place((40, -20, -THICKNESS / 2), (0, -15, -10))),
        dimensional_location("thickness", BOTTOM, TOP, tolerance={thickness_tolerance},
                             presentation=place((50, 30, 0), (15, 0, 0))),
        flatness_tolerance("top-flatness", TOP, 0.05, presentation=place((-30, 20, THICKNESS / 2), (0, 15, 0))),
        dimensional_size("hole-diameter", HOLE_FACE, tolerance=plus_minus_tolerance(0.1, 0),
                         presentation=place((RADIUS, 0, THICKNESS / 2), (15, 15, 0))),
        position_tolerance("hole-position", HOLE_FACE, 0.1, datums=["A"],
                           presentation=place((-RADIUS, 0, THICKNESS / 2), (-15, 15, 0))),
        # The hole's true position: basic distances from the front and the left side to its axis.
        dimensional_location("hole-from-front", FRONT, HOLE_FACE, basic=True,
                             presentation=place((0, -15, THICKNESS / 2), (6, 0, 0))),
        dimensional_location("hole-from-left", LEFT, HOLE_FACE, basic=True,
                             presentation=place((-25, 0, THICKNESS / 2), (0, 6, 0))),{definition}
    )


if __name__ == "__main__":
    edit_plate()
'''

# v4's model-based definition, after the v1 plate's own annotations.
DEFINITION = '''
        surface_profile_tolerance("hole-profile", HOLE_FACE, 0.2, datums=["A"],
                                  presentation=place((0, RADIUS, THICKNESS / 2), (0, 15, 15))),
        # Note 1: every face nothing else controls (here the four sides) within 0.5 of true, to A.
        general_profile("general", 0.5, datums=["A"]),
        note("edges", NOTES["edges"]),
        note("mask", NOTES["primer-mask"], faces=[HOLE_FACE], annotations=["hole-diameter"],
             presentation=place((0, -RADIUS, THICKNESS / 2), (0, -15, 15))),
        # A section through the hole's axis; the far side kept (invert), so the front camera sees the cut.
        view("A-A", camera="front", shows=["hole-diameter", "hole-position", "hole-profile", "mask"],
             section=section("y", 0, invert=True),
             place={"hole-diameter": place((RADIUS, 0, 0), (15, 0, 10))}),
        view("iso", camera="iso"),'''

VERSIONS = {"v1": (10, "round", 5, "plus_minus_tolerance(0.2)", ""),
            "v2": (12, "round", 6, "plus_minus_tolerance(0.2)", ""),
            "v3": (12, "square", 6, "plus_minus_tolerance(0.2)", ""),
            "v4": (10, "round", 5, "limits(9.8, 10.2)", DEFINITION)}


def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="pmi-plate-"))
    try:
        for version, (thickness, hole, radius, tolerance, definition) in VERSIONS.items():
            source = MODEL.format(thickness=thickness, hole=hole, radius=radius, thickness_tolerance=tolerance,
                                  definition=definition)
            (folder / "edit_plate.py").write_text(source, encoding="utf-8")
            # Its one model built as a program's call of it builds it, its declared xbf written (as the
            # engine's own goldens are: ``tests/python/packages/cadgen/engine/test_kinematics.py``).
            reports = engine_build.build(folder / "edit_plate.py", ["edit_plate"], cwd=folder)
            assert all(report["ok"] for report in reports), reports
            server = Server(port=0, mesh_mode="inline")
            try:
                doc = server.document(server.add(folder / "edit_plate.xbf"))
                server.mesh_all(doc, None)
                structure = server.structure(doc)
                structure["path"] = "pmi_plate.xbf"
                out = HERE / version
                shutil.rmtree(out, ignore_errors=True)
                out.mkdir()
                for prototype in structure["prototypes"]:
                    (out / f"{prototype['key']}.xbm").write_bytes(server.cache.get(prototype["key"]))
                (out / "structure.json").write_text(json.dumps(structure, indent=1) + "\n", encoding="utf-8")
            finally:
                server.stop()
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    main()
