"""Native contact graph and exact same-frame host interference for guide pieces."""
import sys,json,os,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent;sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.layout import FINGERS,finger_fan_matrix,THUMB_CMC
from lib.assembly import matrix_location
from check_guide_mount_mutual import leaves
from check_remaining_guide_routes import frame
from check_middle_hardware_paths import bbox_gap
from check_guide_combs import common_volume
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_IN,TopAbs_ON
from OCP.gp import gp_Pnt

def host_for(fr):
 from lib.universal_carrier import make_universal_carrier
 from lib.phalanx import make_phalanx
 from lib.thumb_metacarpal import make_thumb_metacarpal
 from lib.palm_frame import make_palm_frame_bodies,make_little_metacarpal
 from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier
 base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
 if fr=='forearm':return make_wrist_fixed_fork()
 if fr=='wrist_abduction':return make_wrist_yaw_carrier()
 if fr=='wrist_flexion':
  if os.environ.get('GUIDE_AUDIT_PALM_HOST'):return leaves(read_step(ROOT/'STEP/anthropomorphic_hand'/os.environ['GUIDE_AUDIT_PALM_HOST']))[0]
  return next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss')
 if fr=='palm_cup':
  from lib.cup_guide_mounts import _cup_host
  return _cup_host()
 if fr=='thumb_cmc_abduction':return base*make_universal_carrier(phalanx_width=19,yaw_plane=9.5)
 if fr=='thumb_mcp_abduction':return base*bd.Pos(0,36,0)*make_universal_carrier(phalanx_width=16)
 if fr=='thumb_cmc_flexion':return base*make_thumb_metacarpal()
 if fr=='thumb_mcp_flexion':return base*bd.Pos(0,36,0)*make_phalanx(27,16)
 f=next(f for f in FINGERS if fr==f.name+'_mcp_abduction')
 return matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)*make_universal_carrier(phalanx_width=f.widths[0])

if __name__=='__main__':
 name=sys.argv[1];files=[ROOT/'STEP/anthropomorphic_hand'/f for f in sys.argv[2:]];step_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files};parts=[p for f in files for p in leaves(read_step(f))];rows=[]
 for fr in sorted({frame(p.label) for p in parts}):
  selected=[p for p in parts if frame(p.label)==fr];host=host_for(fr);allp=[host,*selected];bbs=[p.bounding_box(optimal=False) for p in allp]
  classifiers=[[BRepClass3d_SolidClassifier(s.wrapped) for s in p.solids()] for p in allp];points=[[tuple(v.center()) for v in p.vertices()]+[tuple(e.position_at(t)) for e in p.edges() for t in(.25,.5,.75)] for p in allp]
  def contact(i,j):
   bb=bbs[j];lo=np.array(tuple(bb.min))-.025;hi=np.array(tuple(bb.max))+.025
   for point in points[i]:
    pt=np.array(point)
    if np.any(pt<lo) or np.any(pt>hi):continue
    for c in classifiers[j]:
     c.Perform(gp_Pnt(*point),.025)
     if c.State() in(TopAbs_IN,TopAbs_ON):return True
   return False
  edges=[];bad=[]
  for i in range(1,len(allp)):
   for j in range(i):
    if bbox_gap(bbs[i],bbs[j])>.0251:continue
    joined=contact(i,j) or contact(j,i)
    if not joined and j>0 and ('screw' in allp[i].label or 'screw' in allp[j].label):
     joined=allp[i].distance_to(allp[j])<=.025
    if joined:edges.append([i,j])
    if j==0:
     v=common_volume(allp[i],host)
     if v>1e-7:bad.append({'body':allp[i].label,'host':host.label,'volume_mm3':v})
  linked={0}
  while True:
   update=linked|{a for a,b in edges if b in linked}|{b for a,b in edges if a in linked}
   if update==linked:break
   linked=update
  exact_host_contacts=[]
  for i,p in enumerate(allp):
   if i in linked or bbox_gap(bbs[i],bbs[0])>.0251:continue
   d=p.distance_to(host);exact_host_contacts.append({'body':p.label,'distance_mm':d})
   if d<=.025:edges.append([i,0]);linked.add(i)
  while True:
   update=linked|{a for a,b in edges if b in linked}|{b for a,b in edges if a in linked}
   if update==linked:break
   linked=update
  row={'frame':fr,'body_count':len(selected),'edges':edges,'exact_host_contact_witnesses':exact_host_contacts,'unattached':[p.label for i,p in enumerate(allp) if i not in linked],'host_interferences':bad};rows.append(row)
  result={'pass':all(not r['unattached'] and not r['host_interferences'] for r in rows),'bodies':sum(r['body_count'] for r in rows),'contact_tolerance_mm':.025,'step_sha256':step_hashes,'palm_host':os.environ.get('GUIDE_AUDIT_PALM_HOST'),'palm_host_sha256':hashlib.sha256((ROOT/'STEP/anthropomorphic_hand'/os.environ['GUIDE_AUDIT_PALM_HOST']).read_bytes()).hexdigest() if os.environ.get('GUIDE_AUDIT_PALM_HOST') else None,'rows':rows};(HERE/(name+'_attachment_report.json')).write_text(json.dumps(result,indent=2)+'\n');print(fr,'unattached',row['unattached'],'host_interferences',bad,flush=True)
 if not result['pass']:raise SystemExit(1)
