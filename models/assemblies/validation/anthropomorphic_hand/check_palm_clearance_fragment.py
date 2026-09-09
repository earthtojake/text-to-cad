import sys,json,hashlib,argparse
from pathlib import Path
import numpy as np
V=Path(__file__).resolve().parent;R=V.parents[3];sys.path.insert(0,str(V))
from check_native_reported_contacts import native_shapes
from lib.guide_mounts import guide_end_registry
from lib.layout import MCP_PALM_SUPPORT_PLANES,CMC_PALM_SUPPORT_PLANES
from lib.palm_frame import PALM_MOUNT_CENTERS,PALM_PAD_MOUNTS
from lib.phalanx_r5_boolean import common
from cadgen import build123d as bd
parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('1','2'),default='1');args=parser.parse_args();suffix='' if args.case=='1' else '_'+args.case
p=R/f'models/assemblies/STEP/anthropomorphic_hand/inspected_palm_clearance_fragment{suffix}.step';parts=native_shapes(p)
chip=parts['detached_fragment_1'];retained=parts['retained_body'];bb=chip.bounding_box();lo=np.array(tuple(bb.min));hi=np.array(tuple(bb.max))
def gap(p):return float(np.linalg.norm(np.maximum(np.maximum(lo-np.asarray(p),np.asarray(p)-hi),0.)))
ends=sorted([{'name':e.name,'frame':e.frame,'bbox_gap_mm':gap(e.point),'point':e.point} for e in guide_end_registry() if e.frame=='wrist_flexion'],key=lambda r:r['bbox_gap_mm'])
zones=[]
for x,y in ((-36,101),(-12,105),(12,100),(-35,36)):
 for z in CMC_PALM_SUPPORT_PLANES if x==-35 else MCP_PALM_SUPPORT_PLANES:zones.append((f'bearing_{x}_{y}_{z}',bd.Pos(x,y,z)*bd.Cylinder(4.2,2.2)))
for i,c in enumerate(PALM_MOUNT_CENTERS):zones.append((f'wrist_mount_{i}',bd.Pos(*c)*bd.Cylinder(3.35,3.3)))
for i,c in enumerate(PALM_PAD_MOUNTS):zones.append((f'pad_mount_{i}',bd.Pos(*c)*bd.Cylinder(2.55,2.3)))
for y in (35.,75.):zones.append((f'cup_seat_{y}',bd.Pos(22,y,0)*bd.Cylinder(4.2,2.5,rotation=(90,0,0))))
# Native comb seating rail centerline with its complete 1.3 mm section.
e=bd.Edge.make_bezier((-35,36,-18),(-32.12,34.92,-18),(-28.7216,34.8768,-18),(-25.457984,35.543808,-18))
zones.append(('cmc_parent_comb_seating_rail',bd.sweep(bd.Plane(origin=e.position_at(0),z_dir=e.tangent_at(0))*bd.Circle(1.3),path=e)))
checks=[]
for n,s in zones:
 d=chip.distance_to(s);v=common(chip,s).volume;checks.append({'zone':n,'distance_mm':d,'common_mm3':v})
 print(n,d,v,flush=True)
report={'input_sha256':{str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in (p,Path(__file__))},'scope':'Inspected detached palm shaving against every authored bearing, mount and comb-seat zone plus parent-frame guide mouths. Full revised assembly checks remain separate.','chip_mm3':chip.volume,'retained_mm3':retained.volume,'bounds_mm':[lo.tolist(),hi.tolist()],'nearest_guide_ends':ends[:8],'protected_zones':checks,'protected_zones_clear':all(r['distance_mm']>.025 and r['common_mm3']<1e-7 for r in checks),'guide_mouths_clear':ends[0]['bbox_gap_mm']>3.}
(V/f'palm_clearance_fragment_inspection{suffix}.json').write_text(json.dumps(report,indent=2)+'\n');print('RESULT',report,flush=True)
