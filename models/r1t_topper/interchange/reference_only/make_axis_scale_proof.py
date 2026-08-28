"""Build the minimal Blender axis/scale proof; never engineering geometry."""

import json
from pathlib import Path

import bpy


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "cad_to_blender_stations.json"
BLEND = HERE / "axis_scale_roundtrip_proof.blend"
RESULT = HERE / "axis_scale_roundtrip_result.json"
COLLECTION = "REFERENCE_ONLY__DO_NOT_ENGINEER"
DATUMS = {
    "DATUM_ORIGIN": (0.0, 0.0, 0.0),
    "X_REAR_CHECK": (1462.0, 0.0, 0.0),
    "Y_DRIVER_CHECK": (0.0, 865.0, 0.0),
    "Y_PASSENGER_CHECK": (0.0, -865.0, 0.0),
    "Z_UP_CHECK": (0.0, 0.0, 760.0),
}


def build() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"

    collection = bpy.data.collections.new(COLLECTION)
    scene.collection.children.link(collection)

    for name, location in DATUMS.items():
        marker = bpy.data.objects.new(name, None)
        marker.empty_display_type = "CROSS"
        marker.empty_display_size = 40.0
        marker.location = location
        collection.objects.link(marker)

    for profile in source["profiles"]:
        curve = bpy.data.curves.new(profile["name"], "CURVE")
        curve.dimensions = "3D"
        spline = curve.splines.new("POLY")
        spline.points.add(len(profile["points_mm"]) - 1)
        for point, xyz in zip(spline.points, profile["points_mm"]):
            point.co = (*xyz, 1.0)
        spline.use_cyclic_u = bool(profile["closed"])
        obj = bpy.data.objects.new(profile["name"], curve)
        obj["status"] = source["status"]
        obj["x_mm"] = profile["x_mm"]
        collection.objects.link(obj)

    scene["status"] = source["status"]
    scene["source_checkpoint"] = source["source_checkpoint"]
    scene["axes"] = json.dumps(source["axes"], sort_keys=True)
    scene["origin"] = source["origin"]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))

    roundtrip = []
    max_error = 0.0
    max_x_plane_error = 0.0
    all_closed = True
    all_profile_transforms_identity = True
    for profile in source["profiles"]:
        obj = bpy.data.objects[profile["name"]]
        points = [list(point.co[:3]) for point in obj.data.splines[0].points]
        errors = [
            abs(actual - expected)
            for actual_xyz, expected_xyz in zip(points, profile["points_mm"])
            for actual, expected in zip(actual_xyz, expected_xyz)
        ]
        max_error = max(max_error, *errors)
        max_x_plane_error = max(
            max_x_plane_error,
            *(abs(point[0] - profile["x_mm"]) for point in points),
        )
        closed = obj.data.splines[0].use_cyclic_u
        all_closed = all_closed and closed
        all_profile_transforms_identity = (
            all_profile_transforms_identity
            and tuple(obj.location) == (0.0, 0.0, 0.0)
            and tuple(obj.rotation_euler) == (0.0, 0.0, 0.0)
            and tuple(obj.scale) == (1.0, 1.0, 1.0)
        )
        roundtrip.append(
            {
                "name": profile["name"],
                "x_mm": profile["x_mm"],
                "closed": closed,
                "points_mm": points,
            }
        )

    marker_locations = {
        name: list(bpy.data.objects[name].location) for name in DATUMS
    }
    max_datum_error = max(
        abs(actual - expected)
        for name, expected_xyz in DATUMS.items()
        for actual, expected in zip(marker_locations[name], expected_xyz)
    )
    tolerance = 0.01
    units_pass = (
        scene.unit_settings.system == "METRIC"
        and scene.unit_settings.scale_length == 0.001
        and scene.unit_settings.length_unit == "MILLIMETERS"
    )
    result = {
        "status": source["status"],
        "source_checkpoint": source["source_checkpoint"],
        "blender_version": bpy.app.version_string,
        "units": {
            "system": scene.unit_settings.system,
            "scale_length": scene.unit_settings.scale_length,
            "length_unit": scene.unit_settings.length_unit,
        },
        "axes": source["axes"],
        "origin": source["origin"],
        "datum_markers_mm": marker_locations,
        "profiles": roundtrip,
        "max_abs_roundtrip_error_mm": max_error,
        "max_datum_error_mm": max_datum_error,
        "max_x_plane_error_mm": max_x_plane_error,
        "all_profiles_closed": all_closed,
        "all_profile_transforms_identity": all_profile_transforms_identity,
        "acceptance_tolerance_mm": tolerance,
        "pass": (
            units_pass
            and max_error <= tolerance
            and max_datum_error <= tolerance
            and max_x_plane_error <= tolerance
            and all_closed
            and all_profile_transforms_identity
        ),
    }
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


build()
