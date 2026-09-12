"""Bounded cap relief in R5's otherwise clear thumb reaction arm."""
import hashlib
import json
from pathlib import Path

import numpy as np
from cadgen import build123d as bd, step
from hand_mechanical_candidate import native_parts
from lib.assembly import matrix_location
from lib.finish import finish
from lib.layout import assembled_transforms
from lib.native_integration import ROOT


@step(out='../../STEP/anthropomorphic_hand/thumb_reaction_arm_clearance_r6.step')
def thumb_reaction_arm_clearance_r6():
    from lib.phalanx_r5_boolean import common, cut
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    name = 'thumb_cmc_negative_yaw_outlet_structural_jaw_1'
    other = 'thumb_cmc_yaw_drive_-1_host_cap'
    gatepath = ROOT / 'validation/anthropomorphic_hand/native_reroute_supports_r5_gate.json'
    gate = json.loads(gatepath.read_text())
    assert gate['complete'] and gate['sample_count'] == 225 and not gate['changed_during_audit']
    contacts = [(row, c) for row in gate['rows'] for c in row['collisions']]
    assert len(contacts) == 1 and {contacts[0][1]['a'], contacts[0][1]['b']} == {name, other}
    row, contact = contacts[0]
    folder = ROOT / 'STEP/anthropomorphic_hand'
    oldpath = folder / 'thumb_reaction_arm_clearance_r5.step'
    digest = gate['body_revisions'][other]['step_sha256']
    capath = next(Path(p) for p, h in gate['input_sha256'].items() if p.endswith('.step') and h == digest)
    assert hashlib.sha256(capath.read_bytes()).hexdigest() == digest
    old, cap = native_parts(oldpath)[name], native_parts(capath)[other]
    transforms = assembled_transforms(row['pose'])
    relative = np.linalg.inv(transforms[gate['body_revisions'][name]['frame']]) @ transforms[gate['body_revisions'][other]['frame']]
    obstacle = matrix_location(relative) * cap
    hit = common(old, obstacle)
    assert hit.solids() and hit.volume > 1e-7
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(hit.wrapped, box, False, True)
    x0, y0, z0, x1, y1, z1 = box.Get()
    margin = .025
    pocket = bd.Pos((x0+x1)/2, (y0+y1)/2, (z0+z1)/2) * bd.Box(
        x1-x0+2*margin, y1-y0+2*margin, z1-z0+2*margin)
    result = cut(old, pocket)
    assert len(result.solids()) == 1 and result.is_valid and result.volume > 0
    remainder = common(result, obstacle)
    assert not remainder.solids() or remainder.volume < 1e-7
    report = dict(scope=__doc__, pose=row['pose'], body=name, obstacle=other,
                  native_contact_mm3=hit.volume, pocket_bounds_mm=[x0,y0,z0,x1,y1,z1],
                  pocket_margin_mm=margin, removed_volume_mm3=old.volume-result.volume,
                  input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__), gatepath, oldpath, capath)}, pass_=True)
    (ROOT / 'validation/anthropomorphic_hand/thumb_reaction_arm_clearance_r6_build.json').write_text(json.dumps(report, indent=2)+'\n')
    return bd.Compound(label='thumb_reaction_arm_R6_cap_relief', children=[finish(result.solids()[0], 'aluminum', name)])


if __name__ == '__main__':
    thumb_reaction_arm_clearance_r6()
