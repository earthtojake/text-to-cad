# Deliberately NOT named `.step.py`. The viewer's catalog scanner treats that suffix as a
# STEP entry, which put a solid model in a drawings folder and invited a name collision
# with the sibling `clamp_plate.dxf.py`. This is a helper module the drawing generator
# path-loads, not a model in its own right.
# Prompt: Flat clamp plate with rounded corners, two clamping bolt holes, and
# a central adjustment slot.

from __future__ import annotations

from build123d import (
    BuildPart,
    BuildSketch,
    Circle,
    Locations,
    Mode,
    RectangleRounded,
    SlotOverall,
    extrude,
)

LENGTH_MM = 70.0
WIDTH_MM = 40.0
THICKNESS_MM = 6.0
CORNER_RADIUS_MM = 6.0
BOLT_HOLE_DIAMETER_MM = 6.5
BOLT_SPACING_MM = 52.0
SLOT_LENGTH_MM = 24.0
SLOT_WIDTH_MM = 8.0


def _plate():
    with BuildPart() as part:
        with BuildSketch():
            RectangleRounded(LENGTH_MM, WIDTH_MM, CORNER_RADIUS_MM)
            with Locations((-BOLT_SPACING_MM / 2.0, 0.0), (BOLT_SPACING_MM / 2.0, 0.0)):
                Circle(BOLT_HOLE_DIAMETER_MM / 2.0, mode=Mode.SUBTRACT)
            SlotOverall(SLOT_LENGTH_MM, SLOT_WIDTH_MM, mode=Mode.SUBTRACT)
        extrude(amount=THICKNESS_MM)
    return part.part


def gen_step():
    return _plate()


def build_dxf():
    import ezdxf
    from cadgen import flatten

    document = ezdxf.new("R2010")
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT")

    faces = flatten.planar_faces(
        _plate(),
        normal_axis="z",
        normal_sign=1.0,
        coordinate_axis="z",
        coordinate=THICKNESS_MM,
    )
    geometry = flatten.union_projected_faces([(faces, lambda v: (v.X, v.Y))])
    flatten.add_shapely_geometry(modelspace, geometry, layer="CUT")
    return document
