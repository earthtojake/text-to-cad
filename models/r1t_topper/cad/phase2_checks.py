"""Deterministic checks for the conceptual Phase 2 master envelope."""

from math import isclose

from parameters import (
    DESIGN_DECISION,
    PLACEHOLDER_REQUIRING_SCAN,
    bed_anchor_interface_dimensions,
    bed_anchor_locations,
    bed_control_button_locations,
    bed_inside_length,
    bed_rail_outer_width,
    bed_rail_section_width,
    cab_roof_height_at_rear,
    cab_roof_width_at_rear,
    cab_to_topper_nominal_gap,
    factory_crossbar_mount_interface_dimensions,
    topper_base_outer_width,
    topper_front_height,
    topper_overall_length,
    topper_rear_clearance,
    value,
)
from topper_envelope import make_master_topper_envelope


def _close(actual: float, expected: float) -> None:
    assert isclose(actual, expected, abs_tol=1e-6), (actual, expected)


def run() -> None:
    bounds = make_master_topper_envelope().bounding_box()
    _close(bounds.min.X, value(cab_to_topper_nominal_gap))
    _close(bounds.max.X, value(bed_inside_length) - value(topper_rear_clearance))
    _close(bounds.size.X, value(topper_overall_length))
    _close(bounds.size.Y, value(topper_base_outer_width))
    _close(bounds.min.Z, 0.0)
    _close(bounds.max.Z, value(topper_front_height))
    assert topper_overall_length.provenance == DESIGN_DECISION

    scan_required = (
        bed_rail_outer_width,
        bed_rail_section_width,
        cab_roof_height_at_rear,
        cab_roof_width_at_rear,
        bed_anchor_locations,
        bed_anchor_interface_dimensions,
        bed_control_button_locations,
        factory_crossbar_mount_interface_dimensions,
    )
    assert all(item.provenance == PLACEHOLDER_REQUIRING_SCAN for item in scan_required)


if __name__ == "__main__":
    run()
    print("PHASE_2_CONCEPT_ENVELOPE_CHECKS_PASS")
