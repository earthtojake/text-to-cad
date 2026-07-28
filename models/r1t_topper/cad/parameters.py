"""Single source of truth for R1T topper dimensions.

Units are millimetres, degrees, kilograms, or newtons as noted. No value in
this file has been physically measured yet. Manufacturer-reference values are
useful envelope inputs, but mounting geometry still requires direct measurement
or a scan before fitment work.

Global coordinates:
    X = vehicle length, positive rearward
    Y = vehicle width, positive driver side
    Z = vertical, positive upward
    origin = vehicle centerline at the forward edge of the bed-rail mounting plane
"""

from dataclasses import dataclass
from typing import Any


MEASURED = "MEASURED"
MANUFACTURER_REFERENCE = "MANUFACTURER REFERENCE"
ESTIMATED = "ESTIMATED"
DESIGN_DECISION = "DESIGN DECISION"
PLACEHOLDER_REQUIRING_SCAN = "PLACEHOLDER REQUIRING SCAN"
PROVENANCE = {
    MEASURED,
    MANUFACTURER_REFERENCE,
    ESTIMATED,
    DESIGN_DECISION,
    PLACEHOLDER_REQUIRING_SCAN,
}


@dataclass(frozen=True)
class Parameter:
    value: Any
    unit: str
    provenance: str
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(f"unsupported provenance: {self.provenance}")


def value(parameter: Parameter) -> Any:
    return parameter.value


# VEHICLE REFERENCE
vehicle_centerline = Parameter(0.0, "mm", DESIGN_DECISION, "coordinate convention")
bed_inside_length = Parameter(
    1377.0,
    "mm",
    MANUFACTURER_REFERENCE,
    "Rivian R1T Upfitting Guide, September 2025, pp. 28 and 30",
    "54.2 in with tonneau open; Rivian's 2022 R1T sizing article gives a rounded 54 in",
)
bed_inside_width = Parameter(
    1299.0,
    "mm",
    MANUFACTURER_REFERENCE,
    "Rivian R1T Upfitting Guide, September 2025, pp. 28 and 30",
    "exposed cargo width; applicability to the target 2022 vehicle requires physical confirmation",
)
bed_rail_outer_width = Parameter(
    1730.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "visual proportion only"
)
bed_rail_height = Parameter(
    90.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "simplified reference envelope"
)
bed_rail_section_width = Parameter(
    145.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "derived provisional rail section"
)
bed_floor_depth_below_rail = Parameter(
    465.0,
    "mm",
    MANUFACTURER_REFERENCE,
    "Rivian R1T Upfitting Guide, September 2025, pp. 28 and 30",
    "maximum bed height; applicability to the target 2022 vehicle requires physical confirmation",
)
cab_roof_height_at_rear = Parameter(
    760.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "reference-image proportion"
)
cab_roof_width_at_rear = Parameter(
    1750.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "reference-image proportion"
)
cab_rear_surface_angle = Parameter(
    8.0, "deg", PLACEHOLDER_REQUIRING_SCAN, "not applied to Checkpoint 1 block envelope"
)
cab_to_topper_nominal_gap = Parameter(
    0.0,
    "mm",
    DESIGN_DECISION,
    "concept envelope covers the bed plane from its forward edge",
    "zero layout offset is not a production contact, seal, or clearance specification",
)
tailgate_height = Parameter(
    510.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "reference-image proportion"
)
tailgate_width = Parameter(
    1570.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "reference-image proportion"
)
tailgate_thickness = Parameter(
    85.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "motion-envelope placeholder"
)
rear_light_clearance = Parameter(
    (70.0, 1480.0, 70.0),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "simplified OEM rear-light keep-out",
)
bed_anchor_locations = Parameter(
    ((170.0, 780.0, -45.0), (170.0, -780.0, -45.0),
     (950.0, 780.0, -45.0), (950.0, -780.0, -45.0)),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "factory anchor positions require direct measurement",
)
bed_anchor_interface_dimensions = Parameter(
    (55.0, 35.0, 30.0),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "factory anchor interface envelope only",
)
bed_control_button_locations = Parameter(
    ((160.0, 820.0, 0.0), (900.0, 820.0, 0.0)),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "driver-side controls require measurement",
)
bed_control_keepout_size = Parameter(
    (110.0, 90.0, 70.0),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "service-access envelope",
)
factory_crossbar_mount_locations = Parameter(
    ((-650.0, 0.0, 785.0), (-250.0, 0.0, 785.0),
     (350.0, 0.0, 785.0), (850.0, 0.0, 785.0)),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "two cab and two topper reference stations",
)
factory_crossbar_mount_interface_dimensions = Parameter(
    (70.0, 45.0, 28.0),
    "mm (X,Y,Z)",
    PLACEHOLDER_REQUIRING_SCAN,
    "exact Rivian interface not modeled",
)

# TOPPER ENVELOPE
topper_rear_clearance = Parameter(
    0.0,
    "mm",
    DESIGN_DECISION,
    "concept rear face shares the tailgate outer plane",
    "zero layout offset is not a production seal or tailgate clearance",
)
topper_overall_length = Parameter(
    1462.0,
    "mm",
    DESIGN_DECISION,
    "manufacturer-reference bed length plus provisional tailgate thickness",
    "concept envelope only; scan the target vehicle before fitment work",
)
topper_base_outer_width = Parameter(
    1730.0,
    "mm",
    DESIGN_DECISION,
    "provisional match to scan-required rail outer-width envelope",
    "not a production contact width",
)
topper_front_height = Parameter(
    760.0,
    "mm",
    DESIGN_DECISION,
    "provisional cab-roof continuation",
    "cab curvature and trailing roof section remain scan-required",
)
topper_rear_height = Parameter(
    745.0,
    "mm",
    DESIGN_DECISION,
    "provisional R1S-like rear roof-corner drop",
    "visual estimate; the roof stays nearly level ahead of the rear corner",
)
roof_crown = Parameter(35.0, "mm", DESIGN_DECISION, "provisional drainage crown")
topper_silhouette_stations = Parameter(
    (
        # x fraction, height, base width, shoulder width, roof width, crown
        (0.00, 760.0, 1730.0, 1690.0, 1570.0, 35.0),
        (0.22, 759.0, 1730.0, 1688.0, 1569.0, 35.0),
        (0.52, 758.0, 1730.0, 1684.0, 1566.0, 35.0),
        (0.78, 755.0, 1730.0, 1672.0, 1558.0, 34.0),
        (1.00, 745.0, 1730.0, 1630.0, 1510.0, 32.0),
    ),
    "(length fraction, mm height, mm widths, mm crown)",
    ESTIMATED,
    "visual approximation from operator-supplied R1S side and rear reference screenshots",
    "near-parallel roof edges and a localized rear-corner taper; replace with registered scan slices",
)
rear_hatch_opening_width = Parameter(1450.0, "mm", DESIGN_DECISION, "provisional")
rear_hatch_opening_height = Parameter(620.0, "mm", DESIGN_DECISION, "provisional")
rear_hatch_angle = Parameter(4.0, "deg", DESIGN_DECISION, "provisional")
wall_nominal_thickness = Parameter(22.0, "mm", DESIGN_DECISION, "sandwich total")
sandwich_core_thickness = Parameter(20.0, "mm", DESIGN_DECISION, "provisional")
carbon_skin_thickness = Parameter(1.0, "mm", DESIGN_DECISION, "each skin, provisional")
base_rail_height = Parameter(80.0, "mm", DESIGN_DECISION, "provisional")
base_rail_width = Parameter(70.0, "mm", DESIGN_DECISION, "provisional")

# MODULE SYSTEM
module_bay_count_per_side = Parameter(3, "count", DESIGN_DECISION, "project brief")
module_opening_width = Parameter(285.0, "mm", DESIGN_DECISION, "provisional")
module_opening_height = Parameter(420.0, "mm", DESIGN_DECISION, "provisional")
module_corner_radius = Parameter(30.0, "mm", DESIGN_DECISION, "provisional")
module_frame_depth = Parameter(35.0, "mm", DESIGN_DECISION, "provisional")
module_seal_compression = Parameter(2.0, "mm", DESIGN_DECISION, "provisional")
module_latch_clearance = Parameter(12.0, "mm", DESIGN_DECISION, "provisional")
module_spacing = Parameter(35.0, "mm", DESIGN_DECISION, "provisional")
removable_panel_max_weight = Parameter(8.0, "kg", DESIGN_DECISION, "handling target")

# CROSSBAR SYSTEM
topper_crossbar_station_1 = Parameter(350.0, "mm X", DESIGN_DECISION, "provisional")
topper_crossbar_station_2 = Parameter(850.0, "mm X", DESIGN_DECISION, "provisional")
crossbar_mount_span = Parameter(1550.0, "mm Y", DESIGN_DECISION, "provisional")
crossbar_interface_width = Parameter(
    70.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "factory interface"
)
crossbar_interface_depth = Parameter(
    45.0, "mm", PLACEHOLDER_REQUIRING_SCAN, "factory interface"
)
crossbar_hardpoint_size = Parameter(
    (120.0, 100.0, 20.0), "mm (X,Y,Z)", DESIGN_DECISION, "preliminary envelope"
)
assumed_vertical_design_load = Parameter(
    3000.0, "N", DESIGN_DECISION, "analysis placeholder, not a rating"
)
assumed_dynamic_load_factor = Parameter(
    3.0, "factor", DESIGN_DECISION, "analysis placeholder, not validated"
)

# REAR HATCH
hinge_axis = Parameter(
    ((1080.0, -725.0, 700.0), (1080.0, 725.0, 700.0)),
    "mm endpoints",
    DESIGN_DECISION,
    "provisional",
)
gas_strut_mount_points = Parameter(
    (((1000.0, 700.0, 500.0), (1120.0, 700.0, 260.0)),
     ((1000.0, -700.0, 500.0), (1120.0, -700.0, 260.0))),
    "mm endpoint pairs",
    DESIGN_DECISION,
    "provisional",
)
hatch_open_angle = Parameter(75.0, "deg", DESIGN_DECISION, "provisional")
hatch_mass_estimate = Parameter(16.0, "kg", ESTIMATED, "preliminary mass placeholder")
seal_land_width = Parameter(20.0, "mm", DESIGN_DECISION, "provisional")
brake_light_recess_dimensions = Parameter(
    (55.0, 900.0, 25.0), "mm (X,Y,Z)", DESIGN_DECISION, "provisional"
)
camera_housing_dimensions = Parameter(
    (70.0, 110.0, 55.0), "mm (X,Y,Z)", DESIGN_DECISION, "provisional"
)


def validate_checkpoint_1() -> None:
    """Small deterministic guard against internally contradictory references."""
    assert value(bed_rail_outer_width) > value(bed_inside_width)
    assert value(tailgate_width) < value(bed_rail_outer_width)
    assert value(cab_to_topper_nominal_gap) == 0
    stations = value(factory_crossbar_mount_locations)
    assert len(stations) == 4
    assert all(station[1] == 0.0 for station in stations)
    assert all(station[2] == stations[0][2] for station in stations)
    assert (
        value(cab_to_topper_nominal_gap)
        + value(topper_overall_length)
        + value(topper_rear_clearance)
        == value(bed_inside_length) + value(tailgate_thickness)
    )


validate_checkpoint_1()
