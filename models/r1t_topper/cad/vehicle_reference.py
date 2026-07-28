"""Checkpoint 1 nonproprietary R1T reference envelopes."""

from build123d import Align, Box, Color, Compound, Location
from cadpy.assembly import AssemblyHelper

from parameters import (
    bed_anchor_interface_dimensions,
    bed_anchor_locations,
    bed_control_button_locations,
    bed_control_keepout_size,
    bed_floor_depth_below_rail,
    bed_inside_length,
    bed_inside_width,
    bed_rail_height,
    bed_rail_outer_width,
    bed_rail_section_width,
    cab_roof_height_at_rear,
    cab_roof_width_at_rear,
    cab_to_topper_nominal_gap,
    factory_crossbar_mount_interface_dimensions,
    factory_crossbar_mount_locations,
    rear_light_clearance,
    tailgate_height,
    tailgate_thickness,
    tailgate_width,
    value,
)


REFERENCE_GRAY = Color(0.50, 0.54, 0.58, 0.58)
REFERENCE_DARK = Color(0.22, 0.25, 0.28, 0.68)
KEEP_OUT = Color(1.00, 0.62, 0.08, 0.25)
CROSSBAR = Color(0.08, 0.72, 0.90, 0.75)
ANCHOR = Color(0.92, 0.76, 0.10, 0.95)
LIGHT = Color(0.95, 0.08, 0.08, 0.72)
AXIS_X = Color(0.90, 0.10, 0.10, 1.0)
AXIS_Y = Color(0.10, 0.75, 0.20, 1.0)
AXIS_Z = Color(0.10, 0.30, 0.95, 1.0)


def _box_at(
    size_x: float,
    size_y: float,
    size_z: float,
    x_min: float,
    y_center: float,
    z_min: float,
):
    return Box(
        size_x,
        size_y,
        size_z,
        align=(Align.MIN, Align.CENTER, Align.MIN),
    ).moved(Location((x_min, y_center, z_min)))


def make_bed_envelope() -> Compound:
    length = value(bed_inside_length)
    inside_width = value(bed_inside_width)
    outer_width = value(bed_rail_outer_width)
    rail_height = value(bed_rail_height)
    rail_width = value(bed_rail_section_width)
    floor_depth = value(bed_floor_depth_below_rail)

    floor = _box_at(length, inside_width, 20.0, 0.0, 0.0, -floor_depth)
    floor.label = "R1T_BED_FLOOR_ENVELOPE"
    floor.color = REFERENCE_GRAY

    rails = []
    rail_y = outer_width / 2.0 - rail_width / 2.0
    for side, sign in (("DRIVER", 1.0), ("PASSENGER", -1.0)):
        rail = _box_at(length, rail_width, rail_height, 0.0, sign * rail_y, -rail_height)
        rail.label = f"R1T_{side}_BED_RAIL_ENVELOPE"
        rail.color = REFERENCE_DARK
        rails.append(rail)

    return Compound(label="R1T_BED_ENVELOPE", children=[floor, *rails])


def make_cab_rear_envelope() -> Compound:
    roof_height = value(cab_roof_height_at_rear)
    roof_width = value(cab_roof_width_at_rear)
    cab_depth = 450.0
    cab_lower_z = -400.0

    body = _box_at(cab_depth, roof_width, roof_height - cab_lower_z, -cab_depth, 0.0, cab_lower_z)
    body.label = "R1T_CAB_REAR_WALL_PLACEHOLDER"
    body.color = REFERENCE_GRAY
    roof = _box_at(cab_depth, roof_width, 35.0, -cab_depth, 0.0, roof_height)
    roof.label = "R1T_CAB_ROOF_TRAILING_PLANE"
    roof.color = REFERENCE_DARK
    return Compound(label="R1T_CAB_REAR_ENVELOPE", children=[body, roof])


def make_tailgate_envelope():
    tailgate = _box_at(
        value(tailgate_thickness),
        value(tailgate_width),
        value(tailgate_height),
        value(bed_inside_length),
        0.0,
        -value(tailgate_height),
    )
    tailgate.label = "R1T_TAILGATE_ENVELOPE"
    tailgate.color = REFERENCE_GRAY
    return tailgate


def make_keep_out_zones() -> Compound:
    keepouts = []
    if value(cab_to_topper_nominal_gap) > 0.0:
        gap = _box_at(
            value(cab_to_topper_nominal_gap),
            value(bed_rail_outer_width),
            value(cab_roof_height_at_rear),
            0.0,
            0.0,
            0.0,
        )
        gap.label = "CAB_TOPPER_NON_CONTACT_GAP"
        gap.color = KEEP_OUT
        keepouts.append(gap)

    light_x, light_y, light_z = value(rear_light_clearance)
    light = _box_at(
        light_x,
        light_y,
        light_z,
        value(bed_inside_length) + value(tailgate_thickness) - light_x,
        0.0,
        -95.0,
    )
    light.label = "REAR_LIGHT_CLEARANCE"
    light.color = LIGHT

    button_x, button_y, button_z = value(bed_control_keepout_size)
    button_z_min = -button_z / 2.0
    buttons = []
    for index, (x, y, _z) in enumerate(value(bed_control_button_locations), start=1):
        keepout = _box_at(button_x, button_y, button_z, x - button_x / 2.0, y, button_z_min)
        keepout.label = f"BED_CONTROL_KEEP_OUT_{index}"
        keepout.color = KEEP_OUT
        buttons.append(keepout)

    return Compound(label="KEEP_OUT_ZONES", children=[*keepouts, light, *buttons])


def make_anchor_references() -> Compound:
    size_x, size_y, size_z = value(bed_anchor_interface_dimensions)
    anchors = []
    for index, (x, y, z) in enumerate(value(bed_anchor_locations), start=1):
        anchor = _box_at(size_x, size_y, size_z, x - size_x / 2.0, y, z - size_z / 2.0)
        anchor.label = f"FACTORY_ANCHOR_REFERENCE_{index}"
        anchor.color = ANCHOR
        anchors.append(anchor)
    return Compound(label="FACTORY_ANCHOR_BRACKETS_REFERENCE", children=anchors)


def make_crossbar_reference_planes() -> Compound:
    mount_x, _mount_y, mount_z = value(factory_crossbar_mount_interface_dimensions)
    bar_span = value(cab_roof_width_at_rear)
    bars = []
    for index, (x, _y, z) in enumerate(value(factory_crossbar_mount_locations), start=1):
        bar = _box_at(mount_x, bar_span, mount_z, x - mount_x / 2.0, 0.0, z)
        bar.label = f"CROSSBAR_REFERENCE_{index}_TRANSVERSE_Y"
        bar.color = CROSSBAR
        bars.append(bar)
    return Compound(label="CROSSBAR_REFERENCE_PLANES", children=bars)


def make_coordinate_reference() -> Compound:
    thickness = 14.0
    length = 260.0
    x_axis = _box_at(length, thickness, thickness, 0.0, 0.0, 0.0)
    x_axis.label = "AXIS_X_REARWARD"
    x_axis.color = AXIS_X
    y_axis = _box_at(thickness, length, thickness, 0.0, length / 2.0, 0.0)
    y_axis.label = "AXIS_Y_DRIVER_SIDE"
    y_axis.color = AXIS_Y
    z_axis = _box_at(thickness, thickness, length, 0.0, 0.0, 0.0)
    z_axis.label = "AXIS_Z_UP"
    z_axis.color = AXIS_Z
    return Compound(label="GLOBAL_COORDINATE_REFERENCE", children=[x_axis, y_axis, z_axis])


def build_reference_subassembly() -> Compound:
    reference = AssemblyHelper("00_REFERENCE")
    reference.add(make_bed_envelope(), "R1T_BED_ENVELOPE")
    reference.add(make_cab_rear_envelope(), "R1T_CAB_REAR_ENVELOPE")
    reference.add(make_tailgate_envelope(), "R1T_TAILGATE_ENVELOPE")
    reference.add(make_keep_out_zones(), "KEEP_OUT_ZONES")
    reference.add(make_anchor_references(), "FACTORY_ANCHOR_BRACKETS")
    reference.add(make_crossbar_reference_planes(), "CROSSBAR_REFERENCE_PLANES")
    return reference.build()
