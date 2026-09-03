from __future__ import annotations
from cadgen import step
from math import tau

from cadgen import build123d as bd

from lib.part_common import polar_point, trapezoid_tooth_profile


GEAR_THICKNESS = 8.0
SUN_TEETH = 24
SUN_PITCH_DIAMETER = 48.0
SUN_ROOT_DIAMETER = 42.0
SUN_OUTSIDE_DIAMETER = 54.0
SUN_BORE_DIAMETER = 10.0

PLANET_COUNT = 3
PLANET_TEETH = 18
PLANET_PITCH_DIAMETER = 36.0
PLANET_ROOT_DIAMETER = 31.0
PLANET_OUTSIDE_DIAMETER = 41.0
PLANET_CENTER_RADIUS = 42.0
PLANET_BORE_DIAMETER = 6.8

RING_TEETH = 60
RING_INTERNAL_PITCH_DIAMETER = 120.0
RING_INTERNAL_ROOT_DIAMETER = 126.0
RING_INTERNAL_TIP_DIAMETER = 114.0
RING_OUTSIDE_DIAMETER = 140.0

CARRIER_DIAMETER = 105.0
CARRIER_BOTTOM_Z = -5.0
CARRIER_TOP_Z = -1.0
CARRIER_THICKNESS = CARRIER_TOP_Z - CARRIER_BOTTOM_Z

PIN_DIAMETER = 6.0
PIN_HEIGHT = 14.0
PIN_BOTTOM_Z = -5.0


def _make_external_gear(
    *,
    label: str,
    teeth: int,
    root_diameter: float,
    outside_diameter: float,
    phase: float,
    center: tuple[float, float] = (0.0, 0.0),
    bore_diameter: float | None = None,
    color: bd.Color | None = None,
):
    with bd.BuildPart() as gear:
        with bd.BuildSketch(bd.Plane.XY):
            bd.Polygon(
                trapezoid_tooth_profile(
                    teeth=teeth,
                    root_radius=root_diameter / 2.0,
                    tip_radius=outside_diameter / 2.0,
                    phase=phase,
                ),
                align=None,
            )
        bd.extrude(amount=GEAR_THICKNESS)

        if bore_diameter is not None:
            with bd.Locations(bd.Location((0.0, 0.0, -0.5))):
                bd.Cylinder(
                    radius=bore_diameter / 2.0,
                    height=GEAR_THICKNESS + 1.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.SUBTRACT,
                )

    part = gear.part.moved(bd.Location((center[0], center[1], 0.0)))
    part.label = label
    part.color = color
    return part


def _make_internal_ring_gear():
    with bd.BuildPart() as ring:
        bd.Cylinder(
            radius=RING_OUTSIDE_DIAMETER / 2.0,
            height=GEAR_THICKNESS,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
        )
        with bd.BuildSketch(bd.Plane.XY):
            bd.Polygon(
                trapezoid_tooth_profile(
                    teeth=RING_TEETH,
                    root_radius=RING_INTERNAL_ROOT_DIAMETER / 2.0,
                    tip_radius=RING_INTERNAL_TIP_DIAMETER / 2.0,
                    phase=-tau / RING_TEETH / 2.0,
                    root_span_fraction=0.68,
                    tip_span_fraction=0.34,
                ),
                align=None,
            )
        bd.extrude(amount=GEAR_THICKNESS, mode=bd.Mode.SUBTRACT)
    part = ring.part
    part.label = "ring_gear_60_internal_teeth"
    part.color = bd.Color(0.66, 0.68, 0.70, 1.0)
    return part


def _make_carrier_plate():
    with bd.BuildPart() as carrier:
        with bd.Locations(bd.Location((0.0, 0.0, CARRIER_BOTTOM_Z))):
            bd.Cylinder(
                radius=CARRIER_DIAMETER / 2.0,
                height=CARRIER_THICKNESS,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
            )
    part = carrier.part
    part.label = "carrier_plate"
    part.color = bd.Color(0.52, 0.62, 0.58, 1.0)
    return part


def _make_pin(label: str, center: tuple[float, float]):
    with bd.BuildPart() as pin:
        with bd.Locations(bd.Location((center[0], center[1], PIN_BOTTOM_Z))):
            bd.Cylinder(
                radius=PIN_DIAMETER / 2.0,
                height=PIN_HEIGHT,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
            )
    part = pin.part
    part.label = label
    part.color = bd.Color(0.22, 0.25, 0.29, 1.0)
    return part


def _planet_center(index: int) -> tuple[float, float]:
    return polar_point(PLANET_CENTER_RADIUS, tau * index / PLANET_COUNT)


@step(out="../STEP/planetary_gear_stage.step")
def planetary_gear_stage():
    """Return the simplified planetary gear assembly in millimeters."""
    parts = [
        _make_carrier_plate(),
        _make_internal_ring_gear(),
        _make_external_gear(
            label="sun_gear_24_external_teeth",
            teeth=SUN_TEETH,
            root_diameter=SUN_ROOT_DIAMETER,
            outside_diameter=SUN_OUTSIDE_DIAMETER,
            phase=-tau / SUN_TEETH / 2.0,
            bore_diameter=SUN_BORE_DIAMETER,
            color=bd.Color(0.94, 0.60, 0.22, 1.0),
        ),
    ]

    for index in range(PLANET_COUNT):
        center = _planet_center(index)
        parts.append(
            _make_external_gear(
                label=f"planet_gear_{index + 1}_18_external_teeth",
                teeth=PLANET_TEETH,
                root_diameter=PLANET_ROOT_DIAMETER,
                outside_diameter=PLANET_OUTSIDE_DIAMETER,
                phase=tau * index / PLANET_COUNT,
                center=center,
                bore_diameter=PLANET_BORE_DIAMETER,
                color=bd.Color(0.24, 0.51, 0.76, 1.0),
            )
        )
        parts.append(_make_pin(f"planet_pin_{index + 1}", center))

    return bd.Compound(obj=parts, children=parts, label="simplified_planetary_gear_stage")


if __name__ == "__main__":
    planetary_gear_stage()
