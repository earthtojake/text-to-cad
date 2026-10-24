"""Motorcycle rear shock absorber (coilover damper) assembly.

Layout
------
Single-tube coilover damper in its static design pose.

* Units: millimeters.
* Origin: midpoint of the eye-to-eye span on the damper axis.
* Damper axis: global Z; +Z points from the body toward the piston rod.
* Mounting eye bores run along global Y so the shock drops straight into a
  swingarm/linkage side view drawn in XZ.
* Fixed root: the damper body module. The piston-rod cartridge rides a
  build123d linear joint along Z (`damper_stroke`, the damper's travel); the
  coil spring is seated on the body's lower perch and bears on the rod's
  upper perch where it stands.

`inspect interfere` reports overlaps at every threaded/blind joint (collar
on tube, gland cap, eye shank, rod entering the tube, spring ends on the
seats). Those are accepted static-assembly interpenetrations, not defects;
the only moving joint (rod stroke along Z) stays coaxial and clear.
"""

from __future__ import annotations
from cadgen import model

from math import cos, sin, tau

import build123d as bd



DISPLAY_NAME = "Motorcycle rear shock absorber"


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------


EYE_TO_EYE = 340.0          # mounting bore center to mounting bore center
EYE_BORE_D = 12.0           # bushing bore
EYE_OD = 30.0               # eye outside diameter
EYE_WIDTH = 25.0            # eye width along the bore axis (Y)

BODY_OD = 50.0              # pressure tube outside diameter
BODY_BOTTOM_Z = -140.0
BODY_TOP_Z = 10.0

GLAND_CAP_OD = 54.0         # rod guide / gland nut at the top of the tube
GLAND_CAP_BOTTOM_Z = BODY_TOP_Z - 4.0
GLAND_CAP_TOP_Z = BODY_TOP_Z + 10.0

PRELOAD_COLLAR_OD = 57.0    # threaded preload adjuster ring
PRELOAD_COLLAR_BOTTOM_Z = -18.0
PRELOAD_COLLAR_TOP_Z = 6.0

LOWER_SEAT_OD = 58.0        # lower spring perch, welded to the tube
LOWER_SEAT_BOTTOM_Z = GLAND_CAP_TOP_Z
LOWER_SEAT_TOP_Z = LOWER_SEAT_BOTTOM_Z + 6.0

SPRING_BOTTOM_Z = LOWER_SEAT_TOP_Z          # spring bears on the lower perch
SPRING_HEIGHT = 100.0
SPRING_TOP_Z = SPRING_BOTTOM_Z + SPRING_HEIGHT
SPRING_MEAN_D = 75.0
SPRING_WIRE_D = 9.0
SPRING_TURNS = 6.5

UPPER_SEAT_BOTTOM_Z = SPRING_TOP_Z          # taper seat locked to the rod
UPPER_SEAT_TOP_Z = UPPER_SEAT_BOTTOM_Z + 16.0
UPPER_SEAT_LOCK_OD = 30.0

ROD_D = 12.0                # chrome piston rod
ROD_BOTTOM_Z = 0.0
ROD_TOP_Z = EYE_TO_EYE / 2 - EYE_OD / 2 - 1.0

LOWER_EYE_Z = -EYE_TO_EYE / 2
UPPER_EYE_Z = EYE_TO_EYE / 2

SHANK_BOTTOM_Z = LOWER_EYE_Z + EYE_OD / 2 - 1.0   # forging from eye to tube
SHANK_TOP_Z = BODY_BOTTOM_Z + 3.0

KNOB_D = 11.0               # rebound adjuster clicker on the tube wall
KNOB_AXIS_Z = BODY_BOTTOM_Z + 14.0
KNOB_STICKOUT = 14.0

DAMPER_STROKE = 30.0        # native linear joint travel range


COLORS = {
    "graphite": "#3f3f45",
    "anodized_red": "#ce3f3f",
    "brushed_bronze": "#c4a66f",
    "chrome": "#e5e7ea",
    "pale_aluminum": "#dfe2e1",
    "spring_yellow": "#fddd27",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _part(shape, name, *details, color_name):
    shape.label = ":".join("_".join(str(token).strip().replace(":", "_").split()) for token in (name, *details))
    shape.color = bd.Color(COLORS[color_name])
    return shape


def _axis_cylinder(center, axis, radius, height):
    """Cylinder of given radius/height centered on `center`, axis along `axis`."""
    z_dir = bd.Vector(axis).normalized()
    plane = bd.Plane(origin=center, z_dir=z_dir)
    return bd.Cylinder(radius, height).moved(plane.location)


def _axis_ring(center, axis, outer_r, bore_r, width):
    """Ring: outer cylinder with a through bore, both on the same axis."""
    body = _axis_cylinder(center, axis, outer_r, width)
    bore = _axis_cylinder(center, axis, bore_r, width + 2.0)
    return body - bore


def _mounting_eye(center_z):
    """Ring-form mounting eye with a bushing bore along Y."""
    return _axis_ring(
        (0.0, 0.0, center_z), (0.0, 1.0, 0.0),
        EYE_OD / 2, EYE_BORE_D / 2, EYE_WIDTH,
    )


def _coil_spring(bottom_z, height, mean_d, wire_d, turns, segments_per_turn=24):
    """Compression coil as tangent-aligned overlapping cylinder segments.

    A circle swept along the exact helix is BOP-valid, but the swept surface's
    knot density alone holds the render mesh at ~620k triangles for this size
    spring (a ~76 MB component GLB that crashes headless rendering), and no
    mesh-tolerance override lifts that floor. Sphere-capped chain links
    tessellate lightly but fuse into a self-intersecting solid. Plain cylinders
    extended one wire radius to overlap their neighbours follow the same helix,
    fuse BOP-clean as a single solid, and stay light.
    """
    segments = max(8, round(turns * segments_per_turn))
    r_mean, r_wire = mean_d / 2, wire_d / 2
    points = [
        bd.Vector(
            r_mean * cos(turns * tau * i / segments),
            r_mean * sin(turns * tau * i / segments),
            bottom_z + height * i / segments,
        )
        for i in range(segments + 1)
    ]
    links = [
        _axis_cylinder(
            tuple((start + end) * 0.5), tuple((end - start).normalized()),
            r_wire, (end - start).length + wire_d,
        )
        for start, end in zip(points, points[1:])
    ]
    return links[0].fuse(*links[1:])


# ---------------------------------------------------------------------------
# components
# ---------------------------------------------------------------------------


def _damper_body_children():
    """Fixed root module: pressure tube, lower eye, shank, adjusters."""

    tube = _axis_cylinder(
        (0.0, 0.0, (BODY_BOTTOM_Z + BODY_TOP_Z) / 2), (0.0, 0.0, 1.0),
        BODY_OD / 2, BODY_TOP_Z - BODY_BOTTOM_Z,
    )

    # forged shank flaring from the eye into the tube weld
    shank = bd.Cone(
        bottom_radius=12.0, top_radius=BODY_OD / 2,
        height=SHANK_TOP_Z - SHANK_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (SHANK_BOTTOM_Z + SHANK_TOP_Z) / 2)))

    gland_cap = _axis_ring(
        (0.0, 0.0, (GLAND_CAP_BOTTOM_Z + GLAND_CAP_TOP_Z) / 2), (0.0, 0.0, 1.0),
        GLAND_CAP_OD / 2, ROD_D / 2 + 0.5, GLAND_CAP_TOP_Z - GLAND_CAP_BOTTOM_Z,
    )

    # threaded preload adjuster with two grip grooves
    collar_center_z = (PRELOAD_COLLAR_BOTTOM_Z + PRELOAD_COLLAR_TOP_Z) / 2
    collar = _axis_cylinder(
        (0.0, 0.0, collar_center_z), (0.0, 0.0, 1.0),
        PRELOAD_COLLAR_OD / 2,
        PRELOAD_COLLAR_TOP_Z - PRELOAD_COLLAR_BOTTOM_Z,
    )
    for groove_z in (collar_center_z - 6.0, collar_center_z + 6.0):
        collar = collar - bd.Torus(
            major_radius=PRELOAD_COLLAR_OD / 2, minor_radius=1.3,
        ).moved(bd.Location((0.0, 0.0, groove_z)))

    lower_seat = bd.Cone(
        bottom_radius=LOWER_SEAT_OD / 2, top_radius=SPRING_MEAN_D / 2 - 1.0,
        height=LOWER_SEAT_TOP_Z - LOWER_SEAT_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (LOWER_SEAT_BOTTOM_Z + LOWER_SEAT_TOP_Z) / 2)))

    # rebound clicker knob on the tube wall, pointing out along +X
    knob = _axis_cylinder(
        (BODY_OD / 2 + KNOB_STICKOUT / 2 - 1.0, 0.0, KNOB_AXIS_Z), (1.0, 0.0, 0.0),
        KNOB_D / 2, KNOB_STICKOUT,
    )
    knob = knob - _axis_cylinder(
        (BODY_OD / 2 + KNOB_STICKOUT + 1.0, 0.0, KNOB_AXIS_Z), (1.0, 0.0, 0.0),
        0.6, 2.0,
    )  # screwdriver slot

    return [
        _part(_mounting_eye(LOWER_EYE_Z),
              "mounting_eye", "lower", color_name="pale_aluminum"),
        _part(shank, "eye_shank", color_name="graphite"),
        _part(tube, "pressure_tube", color_name="graphite"),
        _part(gland_cap, "gland_cap", color_name="anodized_red"),
        _part(collar, "preload_adjuster_collar", color_name="brushed_bronze"),
        _part(lower_seat, "lower_spring_seat", color_name="graphite"),
        _part(knob, "rebound_adjuster_knob", color_name="anodized_red"),
    ]


def _piston_rod_children():
    """Moving cartridge: chrome rod, upper eye, upper spring seat."""

    rod = _axis_cylinder(
        (0.0, 0.0, (ROD_BOTTOM_Z + ROD_TOP_Z) / 2), (0.0, 0.0, 1.0),
        ROD_D / 2, ROD_TOP_Z - ROD_BOTTOM_Z,
    )

    upper_seat = bd.Cone(
        bottom_radius=SPRING_MEAN_D / 2 - 1.0, top_radius=ROD_D / 2 + 2.0,
        height=UPPER_SEAT_TOP_Z - UPPER_SEAT_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (UPPER_SEAT_BOTTOM_Z + UPPER_SEAT_TOP_Z) / 2)))
    lock_ring = _axis_ring(
        (0.0, 0.0, UPPER_SEAT_BOTTOM_Z + 3.0), (0.0, 0.0, 1.0),
        UPPER_SEAT_LOCK_OD / 2, ROD_D / 2, 6.0,
    )
    upper_seat = upper_seat + lock_ring

    return [
        _part(rod, "piston_rod", "chrome", color_name="chrome"),
        _part(upper_seat, "upper_spring_seat", color_name="graphite"),
        _part(_mounting_eye(UPPER_EYE_Z),
              "mounting_eye", "upper", color_name="pale_aluminum"),
    ]


def _spring_part():
    return _part(
        _coil_spring(
            SPRING_BOTTOM_Z, SPRING_HEIGHT, SPRING_MEAN_D,
            SPRING_WIRE_D, SPRING_TURNS,
        ),
        "coil_spring", f"{SPRING_WIRE_D:.0f}mm wire",
        color_name="spring_yellow",
    )


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _build():
    body_module = bd.Compound(children=_damper_body_children(), label="damper_body")
    rod_module = bd.Compound(children=_piston_rod_children(), label="piston_rod_cartridge")
    spring = _spring_part()
    spring.label = "coil_spring"

    # damper stroke: the rod slides on the tube axis (static design pose = 0 travel).
    # The moving side is a rigid frame, as build123d's LinearJoint.connect_to takes.
    bd.LinearJoint("damper_stroke", body_module,
                   axis=bd.Axis((0.0, 0.0, GLAND_CAP_TOP_Z), (0.0, 0.0, 1.0)),
                   linear_range=(0.0, DAMPER_STROKE))
    bd.RigidJoint("damper_axis", rod_module, bd.Location((0.0, 0.0, GLAND_CAP_TOP_Z)))
    body_module.joints["damper_stroke"].connect_to(rod_module.joints["damper_axis"], position=0.0)

    # The spring seats on the body's lower perch. Its top coil bears on the
    # rod's upper perch (SPRING_TOP_Z) where it stands, unjointed: the coil
    # compresses with the stroke, and a second rigid seat would weld the rod
    # to the body.
    bd.RigidJoint("lower_perch_face", body_module, bd.Location((0.0, 0.0, SPRING_BOTTOM_Z)))
    bd.RigidJoint("spring_base_coil", spring, bd.Location((0.0, 0.0, SPRING_BOTTOM_Z)))
    body_module.joints["lower_perch_face"].connect_to(spring.joints["spring_base_coil"])

    return bd.Compound(children=[body_module, rod_module, spring], label="motorcycle_shock_absorber")


@model
def motorcycle_shock_absorber():
    return _build()


if __name__ == "__main__":
    motorcycle_shock_absorber()
