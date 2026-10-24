"""Tom rev4: the production arm (shoulder yaw/pitch, elbow pitch/roll, wrist pitch/yaw, jaw).

Ordered 2026-10-10 (manufacturing/sendcutsend_2026-10-10_latest). The derivation
stages in src/stages/ are child models; this root reads them once as
stock, finishes each part, and places every occurrence once
(lib.current_arm_parts) at the folded rest, then re-places the arm at joint zero:
the servo-centre pose, upper arm standing and forearm level (lib.joint_zero).
Its mates become build123d joints on the parts (lib.joints), their presets
configurations, the control showcase's three clips motions (lib.tom_showcase), and
its finishes materials (lib.materials).
"""
from cadgen import model

import sys

from stages.tom2_symmetric_yokes import tom2_symmetric_yokes
from lib.current_arm_parts import configuration,build_current_arm
from lib.current_arm_stock import component_stock
from lib.tom_showcase import add_clips, add_poses, check_occurrence_ids
from lib.joint_limits import with_audited_limits
from lib.joint_zero import rezeroed_kinematics, posed_at_zero
from lib.joints import author_joints
from lib.materials import apply_materials


def kinematics():
    # The datums are the revision layers', measured from joint zero; the limits are the
    # CAD-audited ones.
    return with_audited_limits(rezeroed_kinematics(configuration()['final']))


KINEMATICS=kinematics()


# The occurrence ids the old showcase clips addressed are still pinned and checked below;
# the clips play control/ik/showcase.py's validated performances on the joints
# (lib/tom_showcase.py).
@model
def tom():
    # Imported stock is read once. The stock recipe retains vendor BREP and
    # combines layout transforms without building intermediate native arms.
    stock=component_stock(tom2_symmetric_yokes())
    arm=posed_at_zero(build_current_arm(stock),configuration()['final'])
    check_occurrence_ids(arm)
    # Finished parts: their materials, then the mates (at joint zero) as joints.
    finishes=apply_materials(arm)
    joints=author_joints(arm,KINEMATICS)
    print(f"tom: materials {finishes}; joints placed {len(joints['placed'])}, "
          f"unplaced {joints['unplaced']}, missing {joints['missing']}",file=sys.stderr,flush=True)
    # The mates' presets and the showcase's clips, by joint label (the mates' names).
    add_poses(arm,KINEMATICS)
    return add_clips(arm,KINEMATICS)


if __name__=='__main__':tom()
