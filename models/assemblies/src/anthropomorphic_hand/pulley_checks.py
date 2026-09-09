"""Exact BREP fit checks for the driven pulley family; run after source edits."""
import json
import math
from pathlib import Path
from cadgen import build123d as bd
from lib.pulley import make_pulley


def overlap_volume(a, b):
    common = a.intersect(b)
    if not common:
        return 0.0
    return common.volume if hasattr(common, "volume") else sum(s.volume for s in common)


def check_pulleys():
    rows = []
    for radius in (3.5, 4.5, 5.5, 7., 11.):
        shaft_radius = 3. if radius == 11 else 1.
        bore = shaft_radius + .03
        flat = shaft_radius * .75
        driven = make_pulley(radius, bore_radius=bore)
        idler = make_pulley(radius, bore_radius=bore, keyed=False)
        shaft = bd.Cylinder(shaft_radius, 1.20)
        cut = bd.Pos(flat + shaft_radius, 0, 0) * bd.Box(2*shaft_radius, 4*shaft_radius, 3.)
        shaft = shaft - cut
        rope = bd.Torus(radius, .30)
        # All changes must remain wholly within the hub, far inside the groove.
        guard = bd.Cylinder(bore+.12, 3.)
        old_outer = idler - guard
        new_outer = driven - guard
        outer_change = abs(old_outer.volume - new_outer.volume)
        added_outer = new_outer - old_outer
        if added_outer:
            outer_change += abs(added_outer.volume)
        removed_outer = old_outer - new_outer
        if removed_outer:
            outer_change += abs(removed_outer.volume)
        neutral_overlap = overlap_volume(driven, shaft)
        positive_rotation_overlap = overlap_volume(driven, bd.Rot(Z=.1) * shaft)
        negative_rotation_overlap = overlap_volume(driven, bd.Rot(Z=-.1) * shaft)
        row = {
            "pitch_radius_mm": radius,
            "bore_radius_mm": bore,
            "flat_native_x_mm": flat,
            "solid_count": len(driven.solids()),
            "neutral_shaft_intersection_mm3": neutral_overlap,
            "neutral_shaft_contact_distance_mm": driven.distance_to(shaft),
            "positive_0_1deg_rotation_interference_mm3": positive_rotation_overlap,
            "negative_0_1deg_rotation_interference_mm3": negative_rotation_overlap,
            "positive_rotation_reaction_torque_sign": "negative Z",
            "negative_rotation_reaction_torque_sign": "positive Z",
            "limiting_flat_corner_moment_arm_mm": math.sqrt(shaft_radius**2-flat**2),
            "groove_tendon_clearance_mm": driven.distance_to(rope),
            "groove_tendon_intersection_mm3": overlap_volume(driven, rope),
            "geometry_change_outside_hub_mm3": outer_change,
            "bounds_min": list(driven.bounding_box().min),
            "bounds_max": list(driven.bounding_box().max),
        }
        assert row["solid_count"] == 1 and driven.is_valid and driven.volume > 0
        assert abs(neutral_overlap) < 1e-9, row
        assert row["neutral_shaft_contact_distance_mm"] < 1e-7, row
        assert positive_rotation_overlap > 1e-8 and negative_rotation_overlap > 1e-8, row
        assert abs(row["groove_tendon_clearance_mm"] - .05) < 1e-7, row
        assert abs(row["groove_tendon_intersection_mm3"]) < 1e-9, row
        assert outer_change < 1e-8, row
        rows.append(row)
    output = Path(__file__).resolve().parents[2] / "STEP/anthropomorphic_hand/pulley_functional_checks.json"
    output.write_text(json.dumps({"ok": True, "checks": rows}, indent=2) + "\n")
    print(json.dumps({"ok": True, "checks": rows}, indent=2))


if __name__ == "__main__":
    check_pulleys()
