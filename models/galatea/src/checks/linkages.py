"""Do Galatea's pushrod linkages stay closed, and do the axes meet where the design says?

    cad run src/checks/linkages.py

The mechanism is a tree: each pushrod hangs from its crank, and the pin at its far end
(the shin's horn for the knee, the gimbal's arm for the ankle) is implied. The loop is
closed when that far eye stays on its pin through the whole travel. Both linkages are
parallelograms, so the couplings' fixed ratios close them exactly; this measures it, with
the transmission angle (rod to lever: 90 is best, a linkage is weak below about 25).
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import dims, kin  # noqa: E402


def distance(a, b):
    return math.dist(a, b)


def angle_between(u, v):
    dot = sum(a * b for a, b in zip(u, v))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (math.hypot(*u) * math.hypot(*v))))))


def sweep(control, limits, steps=24):
    low, high = limits
    return [low + (high - low) * k / steps for k in range(steps + 1)]


def closure(name, control, rod_link, pin_link, pin, lever_pivot, limits):
    """Worst gap between the rod's far eye (on `rod_link`) and its pin (on `pin_link`)."""
    worst, angles = 0.0, []
    for value in sweep(control, limits):
        for side in kin.SIDES:
            point = pin if side == "l" else dims.mirror_point(pin)
            pivot = lever_pivot if side == "l" else dims.mirror_point(lever_pivot)
            transforms = kin.link_transforms({f"{side}_{control}": value})
            eye = kin.apply(transforms[f"{side}_{rod_link}"], point)
            target = kin.apply(transforms[f"{side}_{pin_link}"], point)
            worst = max(worst, distance(eye, target))
            if side == "l":
                rod_axis = kin.apply(transforms[f"{side}_{rod_link}"], (point[0], point[1], point[2] + 100.0))
                lever = [t - p for t, p in zip(target, kin.apply(transforms[f"{side}_{pin_link}"], pivot))]
                angles.append(angle_between([a - b for a, b in zip(rod_axis, eye)], lever))
    transmission = [min(a, 180.0 - a) for a in angles]
    print(f"  {name:14s} gap {worst:.2e} mm over {limits[0]:g}..{limits[1]:g} deg; "
          f"transmission angle {min(transmission):.1f}..{max(transmission):.1f} deg")
    return worst


def meet(name, joints):
    """How far apart the named joints' axes pass (0: they meet at one point)."""
    table = kin.all_joints()
    lines = [(table[j][2], table[j][3]) for j in joints]
    worst = 0.0
    for i, (p, u) in enumerate(lines):
        for q, v in lines[i + 1:]:
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            between = [b - a for a, b in zip(p, q)]
            norm = math.hypot(*cross)
            worst = max(worst, abs(sum(a * b for a, b in zip(between, cross))) / norm if norm > 1e-9 else 0.0)
    print(f"  {name:14s} axes pass within {worst:.2e} mm of each other")
    return worst


def main():
    print("linkage closure")
    gaps = [
        closure("knee", "knee", "knee_rod", "shin", dims.KNEE_HORN_PIN, dims.KNEE, dims.KNEE_RANGE),
        closure("ankle pitch", "ankle_pitch", "ankle_rods", "ankle_gimbal", dims.ANKLE_ARM_PIN, dims.ANKLE, (-45.0, 30.0)),
    ]
    print("axes that should meet")
    gaps += [meet("hip", ("l_hip_yaw", "l_hip_roll", "l_hip_pitch")), meet("ankle", ("l_ankle_pitch_pivot", "l_ankle_roll")),
             meet("waist", ("waist_yaw", "waist_roll", "waist_pitch")),
             meet("shoulder", ("l_shoulder_pitch", "l_shoulder_roll", "l_shoulder_yaw"))]
    ok = max(gaps) < 1e-6
    print("OK: the linkages close and the axes meet" if ok else "a linkage opens or an axis misses")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
