"""Are Galatea's drives RobStride's, and do the brackets meet them where RobStride says?

    cad run src/checks/drives.py

For each of the five models, on the maker's own solid (vendor/, fetched by `vendor.py`):

- every mounting screw of a bracket finds one of the maker's tapped holes under it;
- the plate that bolts to the mounting face, and the hub that bolts to the output flange,
  share no volume with the drive;
- the plain envelope the other checks measure in the drive's place holds all of it
  (what of the drive lies outside the envelope), and is how much larger.

Then on the robot: every drive held by cap screws (the RS04, RS03 and RS06, on both sides)
has all of its mounting screws standing over its tapped holes. A drive is not its own
mirror image, so the right side's are the left's turned, and this is where a turn that
left the holes out of line would show.
"""

import math
import re
import sys

import build123d as bd
from cad.build123d import overlap_volume

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import drive_model  # noqa: E402

from galatea import galatea  # noqa: E402
from lib import hardware  # noqa: E402
from lib.dims import ACTUATORS, PLATE_T, SCREWS  # noqa: E402

LOW = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
SLIVER = 0.5            # mm3: what a boolean's own tolerance leaves


def main():
    hw, failures = hardware.Hardware(), 0
    for size, spec in ACTUATORS.items():
        drive, hub = hw.act[size]["housing"], hw.act[size]["rotor"]
        _, count, pitch = spec["mount"]
        plate = bd.Cylinder((spec["ears"] or spec["front"][0]) + 3.0, PLATE_T, align=LOW) - hardware.mount_bores(size, (0, 0, 0), (0, 0, 1))
        # A screw's shank, 4 mm into the mounting face: it finds a hole where there is no metal.
        shanks = max(overlap_volume(bd.Pos(x, y, -4.5) * bd.Cylinder(0.9, 4.0, align=LOW), drive)
                     for x, y in hardware.mount_positions(size))
        seated = max(overlap_volume(hub, drive), overlap_volume(plate, drive))
        shell = hardware.envelope(size)
        outside = sum(solid.volume for solid in (drive - shell).solids())
        excess = shell.volume / drive.volume - 1.0
        ok = shanks < SLIVER and seated < SLIVER and outside < SLIVER
        failures += not ok
        print(f"{size}: {count} mounting screws on {2 * pitch:g} mm, metal under the worst {shanks:.2f} mm3; "
              f"plate and hub in the drive {seated:.2f} mm3; outside its envelope {outside:.2f} mm3, "
              f"the envelope {100 * excess:.1f}% larger; {drive.volume / 1000:.1f} cm3 at {spec['kg']:g} kg"
              + ("" if ok else "   <-- FAILS"), flush=True)
    placed, astray = on_the_robot()
    print(f"on the robot: {placed} drives held by cap screws, {astray} with a screw off its hole")
    failures += astray
    print("OK: the brackets meet RobStride's drives, on the bench and on the robot, and every envelope holds its drive"
          if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


def on_the_robot():
    """(drives held by cap screws, how many of them have a mounting screw off its hole)."""
    placed = astray = 0
    for link in galatea().shape.children:
        screws = [leaf for leaf in link.children if re.fullmatch(r"m\d_screw(_\d+)?", leaf.label or "")]
        for leaf in link.children:
            size = drive_model(leaf.label or "")
            if not size or not hardware._heads_show(ACTUATORS[size]):
                continue
            kind, count, pitch = ACTUATORS[size]["mount"]
            seat = PLATE_T - SCREWS[kind][1]
            frame = (leaf.location * hardware.stood(size).inverse()).inverse()       # the world, as the drive's frame sees it
            angles = []
            for screw in screws:
                at = (frame * screw.location).position
                if abs(at.Z - seat) < 0.6 and abs(math.hypot(at.X, at.Y) - pitch) < 0.6:
                    angles.append(math.degrees(math.atan2(at.Y, at.X)))
            step, first = 360.0 / count, ACTUATORS[size].get("mount_at", 180.0 / count)
            off = [a for a in angles if abs((a - first) % step - 0.0) > 0.1 and abs((a - first) % step - step) > 0.1]
            placed += 1
            if len(angles) != count or off:
                astray += 1
                print(f"  {link.label}/{leaf.label} ({size}): {len(angles)} of {count} screws found, {len(off)} off the holes"
                      + (f", by {min(abs((a - first) % step) for a in off):.2f} degrees" if off else ""))
    return placed, astray


if __name__ == "__main__":
    sys.exit(main())
