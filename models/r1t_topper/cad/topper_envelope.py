"""Phase 2 master topper envelope: concept volume, not fitment geometry."""

from build123d import Color, Compound, Face, Wire, loft
from cadpy.assembly import AssemblyHelper

from parameters import (
    cab_to_topper_nominal_gap,
    roof_crown,
    roof_side_taper,
    topper_base_outer_width,
    topper_front_height,
    topper_overall_length,
    topper_rear_height,
    value,
)


CONCEPT_BLUE = Color(0.10, 0.36, 0.72, 0.42)


def _section(x: float, height: float) -> Face:
    half_base = value(topper_base_outer_width) / 2.0
    half_roof = half_base - value(roof_side_taper)
    edge_z = height - value(roof_crown)
    points = [
        (x, -half_base, 0.0),
        (x, half_base, 0.0),
        (x, half_roof, edge_z),
        (x, 0.0, height),
        (x, -half_roof, edge_z),
    ]
    return Face.make_surface(Wire.make_polygon(points, close=True))


def make_master_topper_envelope():
    """Return the provisional external design volume used for silhouette review."""
    x_front = value(cab_to_topper_nominal_gap)
    x_rear = x_front + value(topper_overall_length)
    envelope = loft(
        [
            _section(x_front, value(topper_front_height)),
            _section(x_rear, value(topper_rear_height)),
        ],
        ruled=True,
    )
    envelope.label = "TOPPER_MASTER_ENVELOPE_CONCEPT_ONLY"
    envelope.color = CONCEPT_BLUE
    return envelope


def build_topper_concept_subassembly() -> Compound:
    concept = AssemblyHelper("10_TOPPER_CONCEPT")
    concept.add(make_master_topper_envelope(), "TOPPER_MASTER_ENVELOPE_CONCEPT_ONLY")
    return concept.build()
