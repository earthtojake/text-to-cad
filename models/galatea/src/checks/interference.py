# /// script
# dependencies = ["embreex", "numpy", "rtree", "trimesh"]
# ///
"""Does anything in Galatea pass through anything else?

    cad run src/checks/interference.py                 as built: inside each link, and link against link
    cad run src/checks/interference.py ready stride    named poses: link against link
    cad run src/checks/interference.py --poses         every named pose
    cad run src/checks/interference.py --limits        every control swept through its travel, alone:
                                                       a joint's own neighbourhood (links within 3 joints);
                                                       or only the controls named after it
    cad run src/checks/interference.py --corners       the joints that share a centre, moved together:
                                                       each group at the corners and edges of its travel
    cad run src/checks/interference.py --motions       every motion, at its waypoints and between them

The verdict is the kernel's: two parts interfere when their solids share volume
(`overlap_volume`, exact, 0 for parts that only touch). The meshes only choose which
pairs it is asked about, and they choose generously: as built and at a named pose, every
pair whose meshes cross or come within their own error of crossing. A sweep or a motion
has hundreds of frames; there every pair whose meshes cross is measured at the frame
where they sit deepest in each other, and at any frame where they sit deeper than a pin
in its bore can. A pair the kernel cannot intersect is reported unmeasured, which fails
the check: it has not been shown clear. `planted.py` shows the check finding a plate
planted through a skin.

The right side is the left's mirror image, so as built a pair with both parts on the
right is its left twin's, and a right control's sweep its left twin's: neither is run.
"""

import itertools
import sys
import time

import build123d  # noqa: F401  (the model needs cad's build123d integration)
from common import DEEP, crossing_depths, interferences, load_parts, near_crossing_pairs, near_pairs, pose_parts

from galatea import galatea
from lib import kin
from lib.poses import MOTIONS, POSES

SWEEP = 8            # steps across each control's travel
# Joints whose axes meet, under one cover that has to clear its neighbours however they lean together.
CORNERS = {"waist": ("waist_yaw", "waist_roll", "waist_pitch"), "neck": ("neck_yaw", "neck_roll", "neck_pitch"),
           "hip": ("l_hip_yaw", "l_hip_roll", "l_hip_pitch"), "shoulder": ("l_shoulder_pitch", "l_shoulder_roll", "l_shoulder_yaw"),
           "wrist": ("l_wrist_roll", "l_wrist_pitch", "l_wrist_yaw"), "ankle": ("l_ankle_pitch", "l_ankle_roll")}
BETWEEN = 4          # frames between two waypoints of a motion


def report(title, overlaps, unmeasured, limit=40):
    print(f"{title}: {len(overlaps)} interference(s)" + (f", {len(unmeasured)} pair(s) unmeasured" if unmeasured else ""),
          flush=True)
    for volume, a, b in overlaps[:limit]:
        print(f"  {volume:9.1f} mm3  {a}  x  {b}")
    for why, a, b in unmeasured[:limit]:
        print(f"  unmeasured  {a}  x  {b}: {why}")
    return len(overlaps) + len(unmeasured)


def control_limits():
    joints, table = kin.all_joints(), kin.couplings()
    for control in kin.controls():
        if control in table:
            spans = [sorted((joints[j][4][0] / r, joints[j][4][1] / r)) for j, r in table[control].items()]
            yield control, max(s[0] for s in spans), min(s[1] for s in spans)
        else:
            yield control, *joints[control][4]


def frames(waypoints):
    """A motion's waypoints and the frames between each two: every control moves in step from
    one waypoint to the next, whatever the ease, so the path between is the straight blend.
    A motion keyed densely (the walk, every twelfth of a second) gets one frame between."""
    keys = [POSES[pose] if isinstance(pose, str) else pose for _, pose in waypoints]
    between = 1 if len(keys) > 12 else BETWEEN
    for a, b in zip(keys, keys[1:]):
        for k in range(between + 1):
            yield {c: a.get(c, 0.0) + (b.get(c, 0.0) - a.get(c, 0.0)) * k / (between + 1) for c in {*a, *b}}
    yield keys[-1]


def sweep(links, poses, skip=None):
    """Interferences over a run of poses: (overlaps, unmeasured), each pair once, at its worst.
    Every pair whose meshes cross somewhere along the run goes to the kernel at the frame
    where they sat deepest, and at once at any frame where they sit deeper than DEEP."""
    worst, overlaps, unmeasured = {}, {}, {}

    def measure(pairs):
        found, failed = interferences(pairs)
        for volume, a, b in found:
            overlaps[a, b] = max(volume, overlaps.get((a, b), 0.0))
        for why, a, b in failed:
            unmeasured[a, b] = why

    for pose in poses:
        pose_parts(links, pose)
        deep = []
        for pair, depth in crossing_depths(near_pairs(links, within=False, skip=skip)):
            key = (pair[0].path, pair[1].path)
            if depth > worst.get(key, (-1.0,))[0]:
                worst[key] = (depth, pose, pair)
            if depth > DEEP:
                deep.append(pair)
        measure(deep)
    for depth, pose, pair in worst.values():              # each crossing pair, where it was deepest
        if depth <= DEEP:
            pose_parts(links, pose)
            measure([pair])
    return (sorted(((v, a, b) for (a, b), v in overlaps.items()), reverse=True),
            [(why, a, b) for (a, b), why in unmeasured.items()])


def main(argv):
    started = time.time()
    links = load_parts(galatea(), exact=True)
    print(f"{sum(len(p) for p in links.values())} parts in {len(links)} links, read in {time.time() - started:.0f} s", flush=True)
    count = 0
    if not argv:
        both_right = lambda a, b: a.startswith("r_") and b.startswith("r_")
        boxed = near_pairs(links, skip=both_right)
        pairs = near_crossing_pairs(boxed)
        print(f"as built: {len(boxed)} pairs of parts whose boxes meet, {len(pairs)} near enough to measure", flush=True)
        count += report("as built", *interferences(pairs, progress=250))
    elif argv[0] == "--limits":
        # A joint's travel is its neighbours' business: the links within three joints of each
        # other. An arm swung into a leg is a whole-body matter, which the poses and motions test.
        distances = kin.link_distances()
        far = lambda a, b: distances[a, b] > 3
        for control, low, high in control_limits():
            if control.startswith("r_") or (argv[1:] and control not in argv[1:]):
                continue
            steps = [{control: low + (high - low) * step / SWEEP} for step in range(SWEEP + 1)]
            overlaps, unmeasured = sweep(links, [pose for pose in steps if abs(pose[control]) > 1e-9], skip=far)
            if overlaps or unmeasured:
                count += report(f"{control} {low:g}..{high:g}", overlaps, unmeasured, limit=8)
            print(f"swept {control} {low:g}..{high:g}", flush=True)
    elif argv[0] == "--corners":
        # One control at a time says nothing of a bow with a lean in it. Each group goes to every
        # corner of its travel and the middle of every edge: all the poses with two or three of
        # its controls at a limit.
        limits = {control: (low, high) for control, low, high in control_limits()}
        distances = kin.link_distances()
        far = lambda a, b: distances[a, b] > 3
        for name, controls in CORNERS.items():
            if argv[1:] and name not in argv[1:]:
                continue
            ends = itertools.product(*[(limits[control][0], 0.0, limits[control][1]) for control in controls])
            poses = [dict(zip(controls, values)) for values in ends if sum(value != 0.0 for value in values) >= 2]
            count += report(f"{name}, {len(poses)} corners and edges", *sweep(links, poses, skip=far), limit=8)
    elif argv == ["--motions"]:
        for name, waypoints, _ in MOTIONS:
            found = report(f"motion {name}", *sweep(links, list(frames(waypoints))), limit=8)
            count += found
    else:
        for name in (POSES if argv == ["--poses"] else argv):
            pose_parts(links, POSES[name])
            boxed = near_pairs(links, within=False)
            pairs = near_crossing_pairs(boxed)
            count += report(f"pose {name} ({len(pairs)} near pairs of {len(boxed)} boxed)", *interferences(pairs, progress=250))
    print(("OK: nothing interferes" if not count else f"{count} interference(s) in all") + f" ({time.time() - started:.0f} s)")
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
