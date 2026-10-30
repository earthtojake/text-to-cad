from __future__ import annotations

# Prompt: A 100 x 60 x 10 mm plate with a 10 mm through-hole at its centre, carrying semantic PMI as a
# model-based definition: datums A (bottom), B (front side) and C (left side), the plate's thickness
# and the hole's diameter with explicit tolerances, the top's flatness, and the hole's position to
# A|B|C, its true position located by basic dimensions from B and C; datum features B and C
# profiled to the datums before them, and every other face held by a general profile to A|B|C
# (Note 1); a general note and a flag note on the hole, their texts the project's notes; and two
# views: section A-A through the hole's axis, and an iso view showing everything.
#
# Every tolerance value below, and every note's text (lib/notes.py), is ILLUSTRATIVE: chosen to
# exercise the PMI export, not taken from any drawing, standard or process capability. Do not
# manufacture to them.

import build123d as bd
from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import step
from cadgen.ap242 import (annotate, datum, dimensional_location, dimensional_size, flatness_tolerance, general_profile,
                          note, place, plus_minus_tolerance, position_tolerance, section, surface_profile_tolerance,
                          view)
from lib.notes import NOTES


@step(out="../STEP/pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
    body.label = "plate"
    body.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    top = body.faces().sort_by(bd.Axis.Z)[-1]
    front = body.faces().sort_by(bd.Axis.Y)[0]
    left = body.faces().sort_by(bd.Axis.X)[0]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return annotate(
        body,
        datum("A", bottom, presentation=place((40, -20, -5), (0, -15, -10))),
        datum("B", front, presentation=place((40, -30, 0), (0, -15, 0))),
        datum("C", left, presentation=place((-50, 20, 0), (-15, 0, 0))),
        # Illustrative: 10 +/-0.2.
        dimensional_location("thickness", bottom, top, tolerance=plus_minus_tolerance(0.2),
                             presentation=place((50, 30, 0), (15, 0, 0))),
        # Illustrative: diameter 10 +0.1/0.
        dimensional_size("hole-diameter", hole, tolerance=plus_minus_tolerance(0.1, 0),
                         presentation=place((5, 0, 5), (15, 15, 0))),
        # Illustrative: flatness 0.05.
        flatness_tolerance("top-flatness", top, 0.05, presentation=place((-30, 20, 5), (0, 15, 0))),
        # Illustrative: position diameter 0.1 to A|B|C.
        position_tolerance("hole-position", hole, 0.1, datums=["A", "B", "C"],
                           presentation=place((-5, 0, 5), (-15, 15, 0))),
        # The hole's true position: basic (theoretically exact) distances from B and C, measured.
        dimensional_location("hole-from-B", front, hole, basic=True, presentation=place((0, -15, 5), (6, 0, 0))),
        dimensional_location("hole-from-C", left, hole, basic=True, presentation=place((-25, 0, 5), (0, 6, 0))),
        # The datum features a general profile leaves to their own controls. Illustrative: B within
        # 0.1 of true to A, C within 0.1 to A|B.
        surface_profile_tolerance("B-profile", front, 0.1, datums=["A"],
                                  presentation=place((-20, -30, 0), (0, -15, 5))),
        surface_profile_tolerance("C-profile", left, 0.1, datums=["A", "B"],
                                  presentation=place((-50, -10, 0), (-15, 0, 5))),
        # Note 1. Illustrative: every face nothing above controls (the back and the right side)
        # within 0.5 of true to A|B|C.
        general_profile("general", 0.5, datums=["A", "B", "C"]),
        # Note 2, a general note, and Note 3, a flag note on the hole and its diameter.
        note("edges", NOTES["edges"]),
        note("mask", NOTES["primer-mask"], faces=[hole], annotations=["hole-diameter"],
             presentation=place((0, -5, 5), (0, -15, 15))),
        # Section A-A across y through the hole's axis, keeping the far side (invert) so the front
        # camera, at -Y, looks at the cut; the hole's diameter drawn on it.
        view("A-A", camera="front", shows=["thickness", "hole-diameter", "hole-position", "hole-from-C", "mask"],
             section=section("y", 0, invert=True),
             place={"hole-diameter": place((5, 0, 0), (15, 0, 10))}),
        view("iso", camera="iso"),  # shows every annotation and note
    )


if __name__ == "__main__":
    pmi_plate()
