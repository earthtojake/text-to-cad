"""Capsule-clearance self-check for lyra digit poses and animation paths.

Stdlib-only. Each digit segment is approximated by a conservative capsule
(segment + radius) in its link frame; a pose is collision-free when every
thumb capsule clears every finger capsule. The named grip poses are tuned
to small POSITIVE clearances (pads kiss at ~+0.7..0.8 mm, never overlap),
and the animation key orders in `lyra.params.js` are chosen so every
adjacent smoothstep blend stays clear:

- pose tour: relaxed -> precision_pinch -> ok_sign -> point ->
  tripod_pinch -> fist (the fist only neighbors tripod/relaxed; blending
  it with pinch/point/ok sweeps the thumb through the index).
- count: the thumb lifts to a hover key before any finger extends and only
  re-wraps after the fingers curl back.

Run after editing poses:

    ./.venv/bin/python -m lyra_parts.clearance   (from models/renders/lyra)

Exits nonzero if any named pose or animation path dips below zero.
"""

from __future__ import annotations

import math

from lyra_parts import chain

# Conservative capsule radii (mm at finger scale 1; see digits.py widths).
FINGER_SCALE = {"index": 1.0, "middle": 1.03, "ring": 0.97, "pinky": 0.88}
PROX_R, MID_R, DIST_R = 7.0, 6.3, 5.2
THUMB_META_R, THUMB_PROX_R, THUMB_DIST_R = 6.8, 6.2, 5.2
FINGER_TIP_SPHERE_R = 4.4  # scaled; distal capsule ends at the tip-sphere center
THUMB_TIP_SPHERE_R = 4.8


def _seg_seg_dist(p1, q1, p2, q2):
    def sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    def dot(a, b):
        return sum(a[i] * b[i] for i in range(3))

    d1, d2, r = sub(q1, p1), sub(q2, p2), sub(p1, p2)
    a, e, f = dot(d1, d1), dot(d2, d2), dot(d2, r)
    if a <= 1e-12 and e <= 1e-12:
        return math.dist(p1, p2)
    if a <= 1e-12:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = dot(d1, r)
        if e <= 1e-12:
            t, s = 0.0, max(0.0, min(1.0, -c / a))
        else:
            b = dot(d1, d2)
            denom = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / denom)) if denom > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    c1 = [p1[i] + d1[i] * s for i in range(3)]
    c2 = [p2[i] + d2[i] * t for i in range(3)]
    return math.dist(c1, c2)


def _mv(rot, v):
    return [sum(rot[i][k] * v[k] for k in range(3)) for i in range(3)]


def digit_capsules(pose_deg: dict[str, float]) -> dict[str, tuple]:
    """{name: (p0, p1, radius)} capsules in the palm frame for a pose."""
    frames = chain.fk_frames(pose_deg)
    caps = {}
    for finger in chain.FINGERS:
        s = FINGER_SCALE[finger]
        prox, mid, tip = chain.SEGMENT_MM[finger]
        spans = (
            ("prox", f"{finger}_proximal", prox, PROX_R * s),
            ("mid", f"{finger}_middle", mid, MID_R * s),
            ("dist", f"{finger}_distal", tip - FINGER_TIP_SPHERE_R * s, DIST_R * s),
        )
        for seg, link, length, radius in spans:
            rot, pos = frames[link]
            tip_pt = [pos[i] + _mv(rot, [0, 0, length])[i] for i in range(3)]
            caps[f"{finger}.{seg}"] = (list(pos), tip_pt, radius)
    spans = (
        ("meta", "thumb_metacarpal", chain.THUMB_METACARPAL_LEN_MM, THUMB_META_R),
        ("prox", "thumb_proximal", chain.THUMB_PROXIMAL_LEN_MM, THUMB_PROX_R),
        ("dist", "thumb_distal", chain.THUMB_TIP_LEN_MM - THUMB_TIP_SPHERE_R, THUMB_DIST_R),
    )
    for seg, link, length, radius in spans:
        rot, pos = frames[link]
        tip_pt = [pos[i] + _mv(rot, [length, 0, 0])[i] for i in range(3)]
        caps[f"thumb.{seg}"] = (list(pos), tip_pt, radius)
    return caps


def worst_clearance(pose_deg: dict[str, float]) -> tuple[float, str, str]:
    """Smallest thumb-vs-finger capsule clearance (mm; negative = overlap)."""
    caps = digit_capsules(pose_deg)
    worst = (math.inf, "", "")
    for tname in ("thumb.meta", "thumb.prox", "thumb.dist"):
        p1, q1, r1 = caps[tname]
        for fname, (p2, q2, r2) in caps.items():
            if fname.startswith("thumb."):
                continue
            d = _seg_seg_dist(p1, q1, p2, q2) - r1 - r2
            if d < worst[0]:
                worst = (d, tname, fname)
    return worst


def _smoothstep(u: float) -> float:
    t = max(0.0, min(1.0, u))
    return t * t * (3 - 2 * t)


def path_worst(pose_a, pose_b, steps: int = 120) -> tuple[float, str, str, float]:
    """Worst clearance along the smoothstep blend a -> b (the sidecar path)."""
    names = [joint["name"] for joint in chain.all_joints()]
    worst = (math.inf, "", "", 0.0)
    for i in range(steps + 1):
        e = _smoothstep(i / steps)
        pose = {n: pose_a[n] + (pose_b[n] - pose_a[n]) * e for n in names}
        d, ca, cb = worst_clearance(pose)
        if d < worst[0]:
            worst = (d, ca, cb, i / steps)
    return worst


# Animation key orders and ripple-wave constants mirrored from lyra.params.js.
TOUR_KEYS = ("relaxed", "precision_pinch", "ok_sign", "point", "tripod_pinch", "fist")
RIPPLE_ORDER = ("index", "middle", "ring", "pinky", "thumb")
RIPPLE_CURL = {"mcp": 30.0, "pip": 40.0, "dip": 22.0, "thumbFlex": 12.0, "thumbMp": 30.0, "thumbIp": 30.0}
RIPPLE_WINDOW = 0.45


def ripple_pose(phase: float, grip: float = 1.0) -> dict[str, float]:
    """Mirror of the sidecar ripplePose: overlapping per-digit curl pulses
    on top of the baked relaxed pose (the tour's opening wave)."""
    p = phase % 1.0
    step = (1.0 - RIPPLE_WINDOW) / (len(RIPPLE_ORDER) - 1)
    pose = dict(chain.named_poses_deg()[chain.BAKED_POSE_NAME])
    for i, digit in enumerate(RIPPLE_ORDER):
        u = (p - i * step) / RIPPLE_WINDOW
        if u <= 0.0 or u >= 1.0:
            continue
        lobe = math.sin(math.pi * u)
        amp = lobe * lobe * grip
        if digit == "thumb":
            pose["thumb_cmc_flex"] += RIPPLE_CURL["thumbFlex"] * amp
            pose["thumb_mp"] += RIPPLE_CURL["thumbMp"] * amp
            pose["thumb_ip"] += RIPPLE_CURL["thumbIp"] * amp
        else:
            pose[f"{digit}_mcp"] += RIPPLE_CURL["mcp"] * amp
            pose[f"{digit}_pip"] += RIPPLE_CURL["pip"] * amp
            pose[f"{digit}_dip"] += RIPPLE_CURL["dip"] * amp
    return pose
COUNT_THUMB_FIST = (92.0, 13.0, 58.0, 74.0)
COUNT_THUMB_HOVER = (50.0, 30.0, 25.0, 20.0)
COUNT_THUMB_OPEN = (20.0, 10.0, 4.0, 4.0)
COUNT_EXTENDED = {
    "index": (2.0, 2.0, 1.0),
    "middle": (2.0, 2.0, 1.0),
    "ring": (4.0, 4.0, 2.0),
    "pinky": (6.0, 6.0, 3.0),
}


def count_key(step: int, thumb) -> dict[str, float]:
    pose = {joint["name"]: 0.0 for joint in chain.all_joints()}
    for i, finger in enumerate(chain.FINGERS):
        mcp, pip_deg, dip = COUNT_EXTENDED[finger] if step >= i + 1 else (78.0, 100.0, 60.0)
        pose[f"{finger}_mcp"] = mcp
        pose[f"{finger}_pip"] = pip_deg
        pose[f"{finger}_dip"] = dip
    yaw, flex, mp, ip = thumb
    pose.update(
        {"thumb_cmc_yaw": yaw, "thumb_cmc_flex": flex, "thumb_mp": mp, "thumb_ip": ip}
    )
    return pose


def count_keys() -> list[dict[str, float]]:
    return [
        count_key(0, COUNT_THUMB_FIST),
        count_key(0, COUNT_THUMB_HOVER),
        count_key(1, COUNT_THUMB_HOVER),
        count_key(2, COUNT_THUMB_HOVER),
        count_key(3, COUNT_THUMB_HOVER),
        count_key(4, COUNT_THUMB_HOVER),
        count_key(5, COUNT_THUMB_OPEN),
        count_key(0, COUNT_THUMB_HOVER),
    ]


def run_checks(verbose: bool = True) -> list[str]:
    """Return a list of failure strings (empty = all poses/paths clear)."""
    failures = []
    poses = chain.named_poses_deg()
    for name, pose in poses.items():
        d, ca, cb = worst_clearance(pose)
        if verbose:
            print(f"pose {name:18s} clearance {d:7.2f} mm ({ca}|{cb})")
        if d < 0:
            failures.append(f"pose {name}: {d:.2f} mm overlap ({ca}|{cb})")
    for i in range(len(TOUR_KEYS)):
        a, b = TOUR_KEYS[i], TOUR_KEYS[(i + 1) % len(TOUR_KEYS)]
        d, ca, cb, u = path_worst(poses[a], poses[b])
        if verbose:
            print(f"tour {a} -> {b}: worst {d:7.2f} mm at u={u:.2f}")
        if d < 0:
            failures.append(f"tour {a}->{b}: {d:.2f} mm overlap at u={u:.2f} ({ca}|{cb})")
    keys = count_keys()
    for i in range(len(keys)):
        a, b = keys[i], keys[(i + 1) % len(keys)]
        d, ca, cb, u = path_worst(a, b)
        if verbose:
            print(f"count seg {i}: worst {d:7.2f} mm at u={u:.2f}")
        if d < 0:
            failures.append(f"count seg {i}: {d:.2f} mm overlap at u={u:.2f} ({ca}|{cb})")
    for a, b in (("relaxed", "fist"), ("relaxed", "precision_pinch")):
        d, ca, cb, u = path_worst(poses[a], poses[b])
        if verbose:
            print(f"loop {a} <-> {b}: worst {d:7.2f} mm at u={u:.2f}")
        if d < 0:
            failures.append(f"loop {a}<->{b}: {d:.2f} mm overlap ({ca}|{cb})")
    worst = (math.inf, "", "", 0.0)
    for i in range(241):
        u = i / 240.0
        d, ca, cb = worst_clearance(ripple_pose(u))
        if d < worst[0]:
            worst = (d, ca, cb, u)
    if verbose:
        print(f"ripple wave: worst {worst[0]:7.2f} mm at u={worst[3]:.2f}")
    if worst[0] < 0:
        failures.append(f"ripple wave: {worst[0]:.2f} mm overlap at u={worst[3]:.2f} ({worst[1]}|{worst[2]})")
    return failures


if __name__ == "__main__":
    import sys

    fails = run_checks()
    if fails:
        print("\nFAILED:")
        for failure in fails:
            print(" ", failure)
        sys.exit(1)
    print("\nall poses and animation paths are collision-free")
