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
    topper_rear_height,
    topper_rear_clearance,
    topper_silhouette_stations,
    roof_crown,
    value,
)
from topper_envelope import make_master_topper_envelope


def _close(actual: float, expected: float) -> None:
    assert isclose(actual, expected, abs_tol=1e-6), (actual, expected)


def run() -> None:
    stations = value(topper_silhouette_stations)
    assert len(stations) == 5
    assert stations[0][0] == 0.0
    assert stations[-1][0] == 1.0
    assert all(a[0] < b[0] for a, b in zip(stations, stations[1:]))
    assert all(a[1] >= b[1] for a, b in zip(stations, stations[1:]))
    assert all(a[2] >= b[2] for a, b in zip(stations, stations[1:]))
    # The R1S visual surrogate stays nearly parallel and level through the
    # bed, then concentrates its taper in the final rear-corner segment.
    assert stations[0][1] - stations[-2][1] <= 5.0
    assert stations[-2][1] - stations[-1][1] >= 10.0
    assert stations[0][4] - stations[-2][4] <= 12.0
    assert stations[-2][4] - stations[-1][4] >= 40.0
    assert topper_silhouette_stations.provenance == "ESTIMATED"
    _close(stations[0][1], value(topper_front_height))
    _close(stations[-1][1], value(topper_rear_height))
    _close(stations[0][2], value(topper_base_outer_width))
    _close(stations[0][5], value(roof_crown))

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
