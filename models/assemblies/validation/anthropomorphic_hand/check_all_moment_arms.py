"""Numerical virtual-work certificate for all24 axes and48 tendon lengths."""
import sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.hand_routing import hand_side_routes
from lib.layout import JOINTS,TENDONS
from lib.path_analysis import path_length
root=Path(__file__).parent
epsilon=.001
rows=[]
for joint in JOINTS:
    a=-epsilon if joint.limits[0]<0 else 0.;b=epsilon
    left={r['name']:path_length(r['path']) for r in hand_side_routes({joint.name:a})}
    right={r['name']:path_length(r['path']) for r in hand_side_routes({joint.name:b})}
    derivatives={name:(right[name]-left[name])/math.radians(b-a) for name in left}
    entries=[]
    for tendon in TENDONS:
        # Pull torque is minus dL/dq; positive route produces positive torque.
        measured=-derivatives[tendon['name']]
        expected=tendon['sign']*joint.drive_radius if tendon['joint']==joint.name else 0.
        entries.append({'tendon':tendon['name'],'moment_arm_mm':measured,'expected_mm':expected,'pass':abs(measured-expected)<1e-4})
    row={'joint':joint.name,'tendons':entries,'positive_drive':any(e['moment_arm_mm']>1 for e in entries),'negative_drive':any(e['moment_arm_mm']<-1 for e in entries),'pass':all(e['pass'] for e in entries)}
    rows.append(row)
    (root/'all_joint_moment_arms.json').write_text(json.dumps({'scope':'Hand-side virtual work; measured wrist transport length is separately compensated at every actuator.','joints':rows,'pass':all(r['pass'] for r in rows)},indent=2)+'\n')
    print(joint.name,'PASS' if row['pass'] else 'FAIL',[(e['tendon'],e['moment_arm_mm'],e['expected_mm']) for e in entries if not e['pass']],flush=True)
assert len(rows)==24 and all(r['pass'] and r['positive_drive'] and r['negative_drive'] for r in rows)
