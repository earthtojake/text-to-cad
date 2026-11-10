# /// script
# dependencies = ["embreex", "numpy", "rtree", "trimesh"]
# ///
"""Does anything in Galatea pass through anything else?

    cad run src/checks/interference.py                 as built: inside every link, and link against link
    cad run src/checks/interference.py ready stride    named poses: link against link
    cad run src/checks/interference.py --poses         every named pose
    cad run src/checks/interference.py --limits        every control swept through its travel, alone:
                                                       a joint's own neighbourhood (links within 3 joints)
    cad run src/checks/interference.py --motions       every motion, at each of its waypoints
"""

import sys
import time

import build123d  # noqa: F401  (the model needs cad's build123d integration)
from common import interferences, load_parts, pose_parts

from galatea import galatea
from lib import kin
from lib.poses import MOTIONS, POSES


SWEEP = 8            # steps across each control's travel


def report(title, found, limit=200):
    print(f"{title}: {len(found)} interference(s)", flush=True)
    for depth, a, b in found[:limit]:
        print(f"  {depth:6.1f} mm deep  {a}  x  {b}")
    return len(found)


def control_limits():
    joints, table = kin.all_joints(), kin.couplings()
    for control in kin.controls():
        if control in table:
            spans = [sorted((joints[j][4][0] / r, joints[j][4][1] / r)) for j, r in table[control].items()]
            yield control, max(s[0] for s in spans), min(s[1] for s in spans)
        else:
            yield control, *joints[control][4]


def main(argv):
    started = time.time()
    links = load_parts(galatea())
    print(f"{sum(len(p) for p in links.values())} parts in {len(links)} links, meshed in {time.time() - started:.0f} s", flush=True)
    count = 0
    if not argv:
        count += report("as built, within links", interferences(links, within=True, between=False))
        count += report("as built, link against link", interferences(links, within=False, between=True))
    elif argv == ["--limits"]:
        # A joint's travel is its neighbours' business: the links within three joints of each
        # other. An arm swung into a leg is a whole-body matter, which the poses and motions test.
        distances = kin.link_distances()
        far = lambda a, b: distances[a, b] > 3
        for control, low, high in control_limits():
            for step in range(SWEEP + 1):
                value = low + (high - low) * step / SWEEP
                if abs(value) > 1e-9:
                    pose_parts(links, {control: value})
                    found = interferences(links, within=False, skip=far)
                    if found:
                        count += report(f"{control} = {value:g}", found, limit=6)
            print(f"swept {control} {low:g}..{high:g}", flush=True)
    elif argv == ["--motions"]:
        # Every waypoint and four frames between each pair: every control moves in step from
        # one waypoint to the next, whatever the ease, so the path between is the straight blend.
        for name, waypoints, _ in MOTIONS:
            frames = [(t, POSES[pose] if isinstance(pose, str) else pose) for t, pose in waypoints]
            found_any = 0
            for (t0, a), (t1, b) in zip(frames, frames[1:]):
                for k in range(5):
                    f = k / 5
                    blend = {c: a.get(c, 0.0) + (b.get(c, 0.0) - a.get(c, 0.0)) * f for c in {*a, *b}}
                    pose_parts(links, blend)
                    found = interferences(links, within=False)
                    if found:
                        found_any += report(f"motion {name} at {t0 + (t1 - t0) * f:.2f} s", found, limit=6)
            pose_parts(links, frames[-1][1])
            found_any += report(f"motion {name}, {len(frames)} waypoints and the frames between", interferences(links, within=False))
            count += found_any
    else:
        for name in (POSES if argv == ["--poses"] else argv):
            pose_parts(links, POSES[name])
            count += report(f"pose {name}", interferences(links, within=False))
    print(("OK: nothing interferes" if not count else f"{count} interference(s) in all") + f" ({time.time() - started:.0f} s)")
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
