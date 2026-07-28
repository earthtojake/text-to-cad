"""Editable visual topper surrogate: concept volume, not fitment geometry."""

from build123d import Color, Compound, Edge, Face, Wire, loft
from cadpy.assembly import AssemblyHelper

from parameters import (
    cab_to_topper_nominal_gap,
    topper_overall_length,
    topper_silhouette_stations,
    value,
)


CONCEPT_BLUE = Color(0.10, 0.36, 0.72, 0.42)


def _section(
    x: float,
    height: float,
    base_width: float,
    shoulder_width: float,
    roof_width: float,
    crown: float,
) -> Face:
    """Create one symmetric scan-replaceable YZ silhouette section."""
    half_base = base_width / 2.0
    half_shoulder = shoulder_width / 2.0
    half_roof = roof_width / 2.0
    shoulder_z = height * 0.72
    roof_edge_z = height - crown

    left_base = (x, -half_base, 0.0)
    right_base = (x, half_base, 0.0)
    right_shoulder = (x, half_shoulder, shoulder_z)
    right_roof = (x, half_roof, roof_edge_z)
    left_roof = (x, -half_roof, roof_edge_z)
    left_shoulder = (x, -half_shoulder, shoulder_z)

    edges = [
        Edge.make_line(left_base, right_base),
        Edge.make_line(right_base, right_shoulder),
        Edge.make_three_point_arc(
            right_shoulder,
            (x, (half_shoulder + half_roof) / 2.0, (shoulder_z + roof_edge_z) / 2.0 + 8.0),
            right_roof,
        ),
        Edge.make_three_point_arc(
            right_roof,
            (x, 0.0, height),
            left_roof,
        ),
        Edge.make_three_point_arc(
            left_roof,
            (x, -(half_shoulder + half_roof) / 2.0, (shoulder_z + roof_edge_z) / 2.0 + 8.0),
            left_shoulder,
        ),
        Edge.make_line(left_shoulder, left_base),
    ]
    return Face.make_surface(Wire(edges))


def make_master_topper_envelope():
    """Return the provisional external design volume used for silhouette review."""
    x_front = value(cab_to_topper_nominal_gap)
    sections = [
        _section(
            x_front + fraction * value(topper_overall_length),
            height,
            base_width,
            shoulder_width,
            roof_width,
            crown,
        )
        for fraction, height, base_width, shoulder_width, roof_width, crown
        in value(topper_silhouette_stations)
    ]
    envelope = loft(
        sections,
        ruled=False,
    )
    envelope.label = "TOPPER_MASTER_ENVELOPE_CONCEPT_ONLY"
    envelope.color = CONCEPT_BLUE
    return envelope


def build_topper_concept_subassembly() -> Compound:
    concept = AssemblyHelper("10_TOPPER_CONCEPT")
    concept.add(make_master_topper_envelope(), "TOPPER_MASTER_ENVELOPE_CONCEPT_ONLY")
    return concept.build()
