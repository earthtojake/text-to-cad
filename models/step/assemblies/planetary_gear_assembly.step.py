from math import cos, pi, sin, tau

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    extrude,
)


# Units: millimeters.
# Origin: sun/ring center on the carrier axis.
# XY: gear plane. +Z: gear and pin axes.

GEAR_THICKNESS = 8.0
GEAR_BOTTOM_Z = 0.0

SUN_TEETH = 24
SUN_PITCH_DIAMETER = 48.0
SUN_ROOT_DIAMETER = 42.0
SUN_OUTSIDE_DIAMETER = 54.0
SUN_BORE_DIAMETER = 10.0

PLANET_TEETH = 18
PLANET_PITCH_DIAMETER = 36.0
PLANET_ROOT_DIAMETER = 31.0
PLANET_OUTSIDE_DIAMETER = 41.0
PLANET_CENTER_RADIUS = 42.0
PLANET_COUNT = 3
PLANET_BORE_DIAMETER = 6.8

EXTERNAL_TOOTH_ROOT_SPAN_FRACTION = 0.42
EXTERNAL_TOOTH_TIP_SPAN_FRACTION = 0.18


def _srgb_channel_to_linear(channel: int) -> float:
    value = channel / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _srgb_color(hex_color: str) -> Color:
    value = hex_color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected #rrggbb color, got {hex_color!r}")
    return Color(
        _srgb_channel_to_linear(int(value[0:2], 16)),
        _srgb_channel_to_linear(int(value[2:4], 16)),
        _srgb_channel_to_linear(int(value[4:6], 16)),
        1.0,
    )


# Match the docs app's dark-mode hero render source colors.
PLANET_COLORS = (
    _srgb_color("#61d4f6"),
    _srgb_color("#a6ea90"),
    _srgb_color("#ed9ee5"),
)

RING_TEETH = 60
RING_INTERNAL_PITCH_DIAMETER = 120.0
RING_INTERNAL_ROOT_DIAMETER = 126.0
RING_INTERNAL_TIP_DIAMETER = 115.0
RING_OUTSIDE_DIAMETER = 140.0
RING_TOOTH_ROOT_SPAN_FRACTION = 0.68
RING_TOOTH_TIP_SPAN_FRACTION = 0.34
RING_COLOR = _srgb_color("#c5adef")
SUN_COLOR = _srgb_color("#fdce76")
CARRIER_COLOR = _srgb_color("#bfcec8")
PIN_COLOR = _srgb_color("#818993")

CARRIER_DIAMETER = 105.0
CARRIER_BOTTOM_Z = -5.0
CARRIER_TOP_Z = -1.0
CARRIER_THICKNESS = CARRIER_TOP_Z - CARRIER_BOTTOM_Z

PIN_DIAMETER = 6.0
PIN_HEIGHT = 14.0
PIN_BOTTOM_Z = -5.0
PIN_CARRIER_CLEARANCE_DIAMETER = 6.4


def _polar_point(radius: float, angle: float) -> tuple[float, float]:
    return (radius * cos(angle), radius * sin(angle))


def _trapezoid_tooth_profile(
    *,
    teeth: int,
    root_radius: float,
    tip_radius: float,
    phase: float,
    root_span_fraction: float = 0.72,
    tip_span_fraction: float = 0.38,
) -> list[tuple[float, float]]:
    """Return a closed-profile point loop with straight-sided schematic teeth."""
    pitch_angle = tau / teeth
    points: list[tuple[float, float]] = []

    for tooth_index in range(teeth):
        center_angle = phase + tooth_index * pitch_angle
        points.extend(
            (
                _polar_point(root_radius, center_angle - root_span_fraction * pitch_angle / 2.0),
                _polar_point(tip_radius, center_angle - tip_span_fraction * pitch_angle / 2.0),
                _polar_point(tip_radius, center_angle + tip_span_fraction * pitch_angle / 2.0),
                _polar_point(root_radius, center_angle + root_span_fraction * pitch_angle / 2.0),
            )
        )

    return points


def _make_external_gear(
    *,
    label: str,
    teeth: int,
    root_diameter: float,
    outside_diameter: float,
    phase: float,
    center: tuple[float, float] = (0.0, 0.0),
    bore_diameter: float | None = None,
    color: Color | None = None,
):
    with BuildPart() as gear:
        with BuildSketch(Plane.XY):
            Polygon(
                _trapezoid_tooth_profile(
                    teeth=teeth,
                    root_radius=root_diameter / 2.0,
                    tip_radius=outside_diameter / 2.0,
                    phase=phase,
                    root_span_fraction=EXTERNAL_TOOTH_ROOT_SPAN_FRACTION,
                    tip_span_fraction=EXTERNAL_TOOTH_TIP_SPAN_FRACTION,
                ),
                align=None,
            )
        extrude(amount=GEAR_THICKNESS)

        if bore_diameter is not None:
            with Locations(Location((0.0, 0.0, -0.5))):
                Cylinder(
                    radius=bore_diameter / 2.0,
                    height=GEAR_THICKNESS + 1.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    part = gear.part.moved(Location((center[0], center[1], GEAR_BOTTOM_Z)))
    part.label = label
    part.color = color
    return part


def _make_internal_ring_gear(*, label: str, phase: float, color: Color | None = None):
    with BuildPart() as ring:
        Cylinder(
            radius=RING_OUTSIDE_DIAMETER / 2.0,
            height=GEAR_THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        with BuildSketch(Plane.XY):
            Polygon(
                _trapezoid_tooth_profile(
                    teeth=RING_TEETH,
                    root_radius=RING_INTERNAL_ROOT_DIAMETER / 2.0,
                    tip_radius=RING_INTERNAL_TIP_DIAMETER / 2.0,
                    phase=phase,
                    root_span_fraction=RING_TOOTH_ROOT_SPAN_FRACTION,
                    tip_span_fraction=RING_TOOTH_TIP_SPAN_FRACTION,
                ),
                align=None,
            )
        extrude(amount=GEAR_THICKNESS, mode=Mode.SUBTRACT)

    part = ring.part
    part.label = label
    part.color = color
    return part


def _make_carrier_plate():
    with BuildPart() as carrier:
        with Locations(Location((0.0, 0.0, CARRIER_BOTTOM_Z))):
            Cylinder(
                radius=CARRIER_DIAMETER / 2.0,
                height=CARRIER_THICKNESS,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        for index in range(PLANET_COUNT):
            center = _polar_point(PLANET_CENTER_RADIUS, tau * index / PLANET_COUNT)
            with Locations(Location((center[0], center[1], CARRIER_BOTTOM_Z - 0.1))):
                Cylinder(
                    radius=PIN_CARRIER_CLEARANCE_DIAMETER / 2.0,
                    height=CARRIER_THICKNESS + 0.2,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    part = carrier.part
    part.label = "carrier_plate"
    part.color = CARRIER_COLOR
    return part


def _make_planet_pin(*, label: str, center: tuple[float, float]):
    with BuildPart() as pin:
        with Locations(Location((center[0], center[1], PIN_BOTTOM_Z))):
            Cylinder(
                radius=PIN_DIAMETER / 2.0,
                height=PIN_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

    part = pin.part
    part.label = label
    part.color = PIN_COLOR
    return part


def _planet_center(index: int) -> tuple[float, float]:
    angle = tau * index / PLANET_COUNT
    return _polar_point(PLANET_CENTER_RADIUS, angle)


def gen_step():
    """Return a labeled simplified planetary gear assembly in millimeters."""
    sun_pitch_angle = tau / SUN_TEETH
    ring_pitch_angle = tau / RING_TEETH

    parts = [
        _make_carrier_plate(),
        _make_internal_ring_gear(
            label="ring_gear_60_internal_teeth",
            phase=-ring_pitch_angle / 2.0,
            color=RING_COLOR,
        ),
        _make_external_gear(
            label="sun_gear_24_teeth",
            teeth=SUN_TEETH,
            root_diameter=SUN_ROOT_DIAMETER,
            outside_diameter=SUN_OUTSIDE_DIAMETER,
            phase=-sun_pitch_angle / 2.0,
            bore_diameter=SUN_BORE_DIAMETER,
            color=SUN_COLOR,
        ),
    ]

    for index in range(PLANET_COUNT):
        planet_angle = tau * index / PLANET_COUNT
        center = _planet_center(index)
        parts.append(
            _make_external_gear(
                label=f"planet_gear_{index + 1}_18_teeth",
                teeth=PLANET_TEETH,
                root_diameter=PLANET_ROOT_DIAMETER,
                outside_diameter=PLANET_OUTSIDE_DIAMETER,
                phase=planet_angle,
                center=center,
                bore_diameter=PLANET_BORE_DIAMETER,
                color=PLANET_COLORS[index],
            )
        )
        parts.append(_make_planet_pin(label=f"planet_pin_{index + 1}", center=center))

    assembly = Compound(
        obj=parts,
        children=parts,
        label="simplified_planetary_gear_assembly",
    )
    return {"shape": assembly, "params": "planetary_gear_assembly.params.js"}
