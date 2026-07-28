"""Small deterministic checks for the Checkpoint 1 reference envelope."""

from math import isclose

from parameters import (
    MANUFACTURER_REFERENCE,
    bed_floor_depth_below_rail,
    bed_inside_length,
    bed_inside_width,
    cab_roof_width_at_rear,
    cab_to_topper_nominal_gap,
    factory_crossbar_mount_interface_dimensions,
    factory_crossbar_mount_locations,
    tailgate_height,
    value,
)
from vehicle_reference import (
    make_crossbar_reference_planes,
    make_keep_out_zones,
    make_tailgate_envelope,
)


def _close(actual: float, expected: float) -> None:
    assert isclose(actual, expected, abs_tol=1e-6), (actual, expected)


def run() -> None:
    assert value(bed_inside_length) == 1377.0
    assert value(bed_inside_width) == 1299.0
    assert value(bed_floor_depth_below_rail) == 465.0
    assert bed_inside_length.provenance == MANUFACTURER_REFERENCE
    assert bed_inside_width.provenance == MANUFACTURER_REFERENCE
    assert bed_floor_depth_below_rail.provenance == MANUFACTURER_REFERENCE

    tailgate = make_tailgate_envelope().bounding_box()
    _close(tailgate.min.X, value(bed_inside_length))
    _close(tailgate.min.Z, -value(tailgate_height))
    _close(tailgate.max.Z, 0.0)

    assert value(cab_to_topper_nominal_gap) == 0.0
    assert all(
        child.label != "CAB_TOPPER_NON_CONTACT_GAP"
        for child in make_keep_out_zones().children
    )

    crossbars = make_crossbar_reference_planes().children
    expected_x, _expected_y, expected_z = value(
        factory_crossbar_mount_interface_dimensions
    )
    stations = value(factory_crossbar_mount_locations)
    assert len(crossbars) == len(stations) == 4
    plane_z = stations[0][2]
    for crossbar, (station_x, station_y, station_z) in zip(crossbars, stations):
        bounds = crossbar.bounding_box()
        _close(bounds.size.X, expected_x)
        _close(bounds.size.Y, value(cab_roof_width_at_rear))
        _close(bounds.size.Z, expected_z)
        _close(bounds.center().X, station_x)
        _close(bounds.center().Y, station_y)
        _close(bounds.min.Z, station_z)
        _close(station_z, plane_z)
        assert bounds.size.Y > 20.0 * bounds.size.X


if __name__ == "__main__":
    run()
    print("CHECKPOINT_1_REFERENCE_CHECKS_PASS")
