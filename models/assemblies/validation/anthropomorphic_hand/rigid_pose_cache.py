"""Exact authored-pose signatures after cancelling shared rigid ancestors.

Frame transforms have a shared left factor through their common ancestor.
It cancels in A^-1 B, including each finger's fixed neutral fan. Therefore only
joint coordinates below that ancestor can change the relative placement.
No computed transform is rounded and no nearby poses are conflated.
"""
from functools import lru_cache
from lib.layout import JOINT_BY_NAME


@lru_cache(maxsize=None)
def joint_chain(frame):
    if frame == 'forearm':
        return ()
    joint = JOINT_BY_NAME[frame]
    return (*joint_chain(joint.parent), frame)


@lru_cache(maxsize=None)
def relative_joints(frame_a, frame_b):
    a, b = joint_chain(frame_a), joint_chain(frame_b)
    shared = 0
    while shared < min(len(a), len(b)) and a[shared] == b[shared]:
        shared += 1
    return tuple(sorted(set(a[shared:]) | set(b[shared:])))


def relative_pose_key(name_a, frame_a, name_b, frame_b, pose):
    names = tuple(sorted((name_a, name_b)))
    return ('authored_relative_pose', *names,
            tuple((joint, float(pose.get(joint, 0.)))
                  for joint in relative_joints(frame_a, frame_b)))
