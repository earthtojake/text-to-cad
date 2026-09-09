"""Neutral anatomy integration study. This is not the complete hand assembly."""
from cadgen import build123d as bd, step
from lib.layout import FINGERS, JOINTS, THUMB_CMC, THUMB_LENGTHS
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley


@step(out="../../STEP/anthropomorphic_hand/anatomy_layout.step")
def anatomy_layout():
    children = []
    for finger in FINGERS:
        y = finger.base_y
        for index, (length, width) in enumerate(zip(finger.lengths, finger.widths)):
            role = ('proximal', 'middle', 'distal')[index]
            part = make_phalanx(length, width, distal=index == 2, label=f'{finger.name}_{role}_frame')
            children.append(bd.Pos(finger.x, y, 0) * part)
            y += length
    station = 0.
    for index, (length, width) in enumerate(zip(THUMB_LENGTHS, (19., 16., 13.))):
        role = ('metacarpal', 'proximal', 'distal')[index]
        part = make_phalanx(length, width, distal=index == 2, label=f'thumb_{role}_frame')
        children.append(bd.Pos(*THUMB_CMC) * bd.Rot(0, 0, 45) * bd.Pos(0, station, 0) * part)
        station += length
    for joint in JOINTS:
        if joint.system in ('wrist', 'palm'):
            continue
        yaw = 'abduction' in joint.name
        spacing = (9.5 if 'cmc' in joint.name else 8.) if yaw else .9
        orient = bd.Plane(origin=joint.origin, z_dir=joint.axis).location
        for sign, side in ((1, 'positive'), (-1, 'negative')):
            pulley = make_pulley(joint.drive_radius, label=f'{joint.name}_{side}_drive_pulley')
            children.append(orient * bd.Pos(0, 0, sign * spacing) * pulley)
    return bd.Compound(label='neutral_anatomy_integration_study', children=children)


if __name__ == '__main__':
    anatomy_layout()
