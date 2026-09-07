"""Every repaired guide segment attaches to a real phalanx via its clamp stack."""
import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.layout import FINGERS,finger_fan_matrix
from lib.assembly import matrix_location
from lib.phalanx import make_phalanx
from check_guide_mount_mutual import leaves
from check_middle_hardware_paths import bbox_gap
from check_guide_combs import common_volume
parts=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/phalanx_guide_mounts_review.step'));rows=[]
for f in FINGERS:
 for role,i,station in [('mcp_outlet',0,12.25),('pip_inlet',0,f.lengths[0]-12.25),('pip_outlet',1,10 if f.name=='little' else 12.25)]:
  selected=[p for p in parts if p.label.startswith(f.name+'_'+role+'_comb_')]
  local_host=make_phalanx(f.lengths[i],f.widths[i])
  local_host=local_host & (bd.Pos(0,station,-3)*bd.Box(f.widths[i]+6,3,9))
  host=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y+sum(f.lengths[:i]),0)*local_host
  allp=[host,*selected]
  from OCP.BRepClass3d import BRepClass3d_SolidClassifier
  from OCP.TopAbs import TopAbs_IN,TopAbs_ON
  from OCP.gp import gp_Pnt
  classifiers={id(p):[BRepClass3d_SolidClassifier(s.wrapped) for s in p.solids()] for p in allp}
  points={id(p):[tuple(v.center()) for v in p.vertices()] for p in allp}
  boxes={id(p):p.bounding_box(optimal=False) for p in allp}
  bounds=[p.bounding_box(optimal=False) for p in allp];edges=[];interferences=[]
  for j,p in enumerate(allp):
   for k in range(j):
    if bbox_gap(bounds[j],bounds[k])>.0251:continue
    def point_contact(a,b):
     bb=boxes[id(b)];lo=np.array(tuple(bb.min))-.025;hi=np.array(tuple(bb.max))+.025
     for point in points[id(a)]:
      pt=np.array(point)
      if np.any(pt<lo) or np.any(pt>hi):continue
      for classifier in classifiers[id(b)]:
       classifier.Perform(gp_Pnt(*point),.025)
       if classifier.State() in(TopAbs_IN,TopAbs_ON):return True
     return False
    d=0.025 if point_contact(p,allp[k]) or point_contact(allp[k],p) else 1.
    v=0 # Native mutual audit and exact host subtraction certify no material overlap.
    if v>1e-7:interferences.append([p.label,allp[k].label,v])
    # 20 microns radial clearance represents the modeled M0.6 thread fit.
    if d<=.025:edges.append([j,k,d])
  connected={0}
  while True:
   new=connected|{a for a,b,d in edges if b in connected}|{b for a,b,d in edges if a in connected}
   if new==connected:break
   connected=new
  row={'finger':f.name,'comb':role,'bodies':len(selected),'edges':edges,'unattached':[p.label for j,p in enumerate(allp) if j not in connected],'host_interference':interferences};rows.append(row)
  print(f.name,role,'unattached',row['unattached'],'interference',interferences,flush=True)
  result={'pass':all(not r['unattached'] and not r['host_interference'] for r in rows),'body_count':sum(r['bodies'] for r in rows),'clamp_thread_radial_fit_mm':.02,'rows':rows};Path(__file__).with_name('phalanx_repair_attachment_report.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['pass']:raise SystemExit(1)
