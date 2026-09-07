"""Certify the little-pad repair is a subset and clears the known fist liner."""
import hashlib,json
from pathlib import Path
from cadgen import build123d as bd
from lib.fingertip_pad import make_fingertip_pad
from lib.phalanx import make_phalanx
from lib.layout import FINGERS,assembled_transforms,finger_fan_matrix
from lib.assembly import matrix_location
from lib.assembled_routing import assembled_finger_routes
from lib.transport_guide import path_wire
from check_global_phalanges import named_poses
from check_fingertip_pads import common_volume

root=Path(__file__).parent
old=make_fingertip_pad('little',16.,11.,radii=(5.75,6.1,2.))
new=make_fingertip_pad('little',16.,11.)
report={'pass':False,'source_sha256':hashlib.sha256(Path('models/assemblies/src/anthropomorphic_hand/lib/fingertip_pad.py').read_bytes()).hexdigest(),'subset':[]}
for a,b in zip(new,old):
    extra=a-b
    row={'body':a.label,'new_volume_mm3':a.volume,'old_volume_mm3':b.volume,'new_outside_old_mm3':extra.volume if extra else 0.}
    row['pass']=row['new_outside_old_mm3']<1e-7
    report['subset'].append(row)
    print('subset',a.label,row,flush=True)
host=make_phalanx(16.,11.,True)
report['mount']={'bridge_host_gap_mm':new[1].distance_to(host),'pad_bridge_gap_mm':new[0].distance_to(new[1]),'screw_bridge_gaps_mm':[p.distance_to(new[1]) for p in new[2:4]],'insert_host_gaps_mm':[p.distance_to(host) for p in new[4:]],'internal_pair_overlap_mm3':[common_volume(a.wrapped,b.wrapped) for i,a in enumerate([host,*new]) for b in [host,*new][i+1:]]}
pose=named_poses()[1][1];f=FINGERS[3];fk=assembled_transforms(pose)
place=matrix_location(fk['little_dip'])*matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y+sum(f.lengths[:2]),0)
group=next(g for r in assembled_finger_routes('little',pose) for g in r['groups'] if g['label']=='little_mcp_flexion_positive_yaw_reaction')
wire=path_wire(group['path'])
report['repaired_full_fist']={'group':group['label'],'pose':pose,'pad_centerline_distance_mm':wire.distance_to(place*new[0]),'outer_radius_mm':.45}
report['repaired_full_fist']['clearance_mm']=report['repaired_full_fist']['pad_centerline_distance_mm']-.45-1e-6
m=report['mount']
report['pass']=all(r['pass'] for r in report['subset']) and max(m['bridge_host_gap_mm'],m['pad_bridge_gap_mm'],*m['screw_bridge_gaps_mm'],*m['insert_host_gaps_mm'])<1e-6 and max(m['internal_pair_overlap_mm3'])<1e-7 and report['repaired_full_fist']['clearance_mm']>0
report['scope']='Only little silicone pad and its carrier change, by shrinking nested XY ellipsoids at fixed center/height; all other pads and hardware are identical. Exact new-minus-old solid tests certify subset containment, so every prior noninterference result remains valid. The only failed full-fist route/body pair is explicitly remeasured against the repaired skin.'
(root/'fingertip_pad_little_repair.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
if not report['pass']:raise SystemExit(1)
