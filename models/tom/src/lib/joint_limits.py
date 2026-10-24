"""Tom rev4's joint limits, audited against the placed CAD. They replace the inherited mate values.

The revision layers carry limits forward from rev3 and the tom2 stages. On 2026-10-10,
tools/robot_description/sweep_limits.py swept every joint through a full servo turn against
the URDF meshes, and exact boolean overlap of the solids confirmed each stop. Two inherited
limits ran into hard interference:
- shoulder yaw ±90: the yaw yoke's lower arm and web turn in the plane of the base carrier
  plate and meet its front edge at 64.3 (64 mm3 of overlap at 90);
- elbow pitch +252: the elbow yoke meets the elbow servo's case at 199.4 (99 mm3 at 252).
(Those angles, like the sweep records, are from the folded rest. Since 2026-10-11 joint zero is
the servo-centre pose, upper arm standing and forearm level (lib/joint_zero.py): shoulder pitch
reads 90 more and elbow pitch 90 less than before, and these limits are in that convention.)
Four others had travel to spare.

Each limit is the first CAD contact less a margin. The margin is 2 deg where both parts are
authored sheet metal, which the model gets exactly. It is 5 deg where a vendor servo model
forms the stop: those models lack real stop features and read a few degrees optimistic
(AGENTS.md). The limits are provisional until the built arm is measured, and auto-calibration
checks them (control/auto_calibrate.py: "fix the limits, not the calibrator").
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass

from lib.mates import revolute
LIMITS_DEG = {
    "shoulderYaw": (-62.0, 62.0),      # yaw yoke (lower arm and web) vs carrier plate front edge:
                                       # contact ±64.3 at any pitch. The OUTER bound: toward the fold
                                       # the lower link meets the yaw servo case far sooner, which is
                                       # control/ik/coupling.py's (the URDF cannot say it)
    "shoulderPitch": (-90.0, 90.0),    # 0: upper arm standing; +90: the folded rest (design
                                       # contact); -90: upper arm level. A straight arm meets the
                                       # table at -97.5; hardware stop -109.4. Over the fold's last
                                       # ~29 deg the lower link's root rubs the yaw yoke (up to
                                       # 1.5 mm3 CAD overlap at 80; none at 90 or 61)
    "elbowPitch": (-90.0, 104.0),      # 0: forearm square to the upper arm; -90: folded on it;
                                       # elbow yoke vs elbow servo case at 109.4 (vendor model)
    "elbowRoll": (-90.0, 90.0),        # link plates vs elbow yoke: contact ±91.2
    "wristPitch": (-98.0, 98.0),       # wrist yoke vs wrist-pitch servo case: contact ±109.4 (vendor
                                       # model). Held to ±98, clear of the planner's sphere model,
                                       # which meets the gripper at +100.25 / -100.5 on the column
    "wristYaw": (-104.0, 104.0),       # jaw servo case vs wrist yoke and screw: -108.8 / +109.4
    "gripperJaw": (0.0, 145.0),        # 0: jaws closed; claw vs fixed jaw frame at 150.1
}


def with_audited_limits(kinematics: dict) -> dict:
    """``kinematics`` with every revolute mate's limits replaced from LIMITS_DEG."""
    mates = []
    for mate in kinematics["mates"]:
        row = asdict(mate) if is_dataclass(mate) else dict(mate)
        if row["kind"] == "revolute":
            if row["name"] not in LIMITS_DEG:
                raise ValueError(f"no audited limit for revolute mate {row['name']!r}")
            mate = revolute(row["name"], parent=row["parent"], child=row["child"],
                            origin=row["axis"]["origin"], direction=row["axis"]["dir"],
                            limits=LIMITS_DEG[row["name"]])
        mates.append(mate)
    names = {asdict(m)["name"] for m in mates if asdict(m)["kind"] == "revolute"}
    if names != set(LIMITS_DEG):
        raise ValueError(f"LIMITS_DEG names {sorted(set(LIMITS_DEG) - names)} that no mate declares")
    return {**kinematics, "mates": mates}
