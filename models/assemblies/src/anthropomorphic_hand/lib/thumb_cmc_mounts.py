"""Frame-anchored split combs at the twelve frozen distal CMC liner datums.

Local CMC coordinates are used inside the factories. Public occurrences are
placed once into the assembled neutral thumb frame and retain their material
frame names for motion. No routing controls are changed by these supports.
"""
import numpy as np
from functools import lru_cache
from cadgen import build123d as bd
from lib.guide_mounts import _finish,_bolt,_sweep
from lib.thumb_cmc_transport import cmc_inlet_contract
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.palm_frame import make_palm_frame_bodies
from lib.layout import THUMB_CMC


@lru_cache(maxsize=1)
def _meta_host():return make_thumb_metacarpal()


def _box(center,size,r=.08):
 s=bd.Pos(*center)*bd.Box(*size)
 return bd.fillet(s.edges(),r)


def _host_clamp(host,x,y,z,side,label,width=2.8,height=2.9):
 outer=_box((x,y,z),(width,1.,height),.10)
 shell=outer
 lower=shell & (bd.Pos(x,y,z-10.01)*bd.Box(20,4,20))
 upper=shell & (bd.Pos(x,y,z+10.01)*bd.Box(20,4,20))
 sx=x+side*(width/2+.72)
 for top in(False,True):
  zz=z+(.40 if top else -.40)
  ear=bd.Pos(sx,y,zz)*bd.Cylinder(.50,.50)
  tab=_box(((sx+x)/2,y,zz),(abs(sx-x)+.65,.88,.50),.055)
  part=(upper if top else lower).fuse(tab,ear)-host
  part=part-(bd.Pos(sx,y,z)*bd.Cylinder(.32,8))
  if top:upper=part
  else:lower=part
 return lower,upper,_bolt(sx,y,z+.65,1.3,label+'_host_M0p6_screw'),(x+side*(width/2-.12),y,z-.85)


def _comb(points,tangent,label,ear_sides=(-1,1),bore=.47):
 points=[np.asarray(p,float) for p in points];xs=[p[0] for p in points];y=points[0][1];z=points[0][2]
 assert all(abs(p[1]-y)<1e-9 and abs(p[2]-z)<1e-9 for p in points)
 rings=[bd.Plane(origin=p,z_dir=tangent).location*bd.fillet(bd.Cylinder(.61,.50).edges(),.025) for p in points]
 # A scalloped common web shares the .043-mm ligaments between the oblique
 # parent bores. Rounded skins retain the exact original bore centres.
 raw=rings[0].fuse(*rings[1:]) if len(rings)>1 else rings[0]
 if len(points)>1:raw=raw.fuse(_box(((min(xs)+max(xs))/2,y,z),(max(xs)-min(xs),.50,1.02),.055))
 lower=raw & (bd.Pos(0,y,z-10.04)*bd.Box(40,5,20));upper=raw & (bd.Pos(0,y,z+10.04)*bd.Box(40,5,20))
 screws=[];ears=[]
 for side in ear_sides:
  c=(max(xs) if side>0 else min(xs))+side*1.05;root=(max(xs) if side>0 else min(xs))
  ears.append((c,y,z))
  for top in(False,True):
   zz=z+(.30 if top else -.30)
   ear=bd.Pos(c,y,zz)*bd.Cylinder(.48,.48)
   bridge=_box(((c+root)/2,y,zz),(abs(c-root)+.3,.50,.40),.035)
   if top:upper=upper.fuse(ear,bridge)
   else:lower=lower.fuse(ear,bridge)
  screws.append(_bolt(c,y,z+.54,1.08,label+f'_liner_{side:+d}_M0p6_screw'))
 cutters=[bd.Plane(origin=p,z_dir=tangent).location*bd.Cylinder(bore,2.5) for p in points]
 if abs(tangent[0])>.1:
  axis=np.asarray(tangent,float)
  for p in points:
   for side in(-1,1):
    cutters.append(bd.Plane(origin=p+side*.70*axis,z_dir=side*axis).location*bd.Cone(bore,1.10,1.20))
 cutters += [bd.Pos(*p)*bd.Cylinder(.32,4) for p in ears]
 for cutter in cutters:lower=lower-cutter;upper=upper-cutter
 return lower,upper,screws,ears,cutters


def _parts_finish(lower,upper,extras,host,cutters,label):
 for cutter in cutters:lower=lower-cutter
 if len(lower.solids())!=1:print(label,[(b.volume,str(b.bounding_box())) for b in lower.solids()],flush=True)
 parts=[_finish(lower,label+'_structural_jaw'),_finish(upper,label+'_scalloped_cap')]
 for p in extras:
  q=_finish(p,p.label or label+'_host_cap','#d0d8df' if 'screw' in p.label else '#9DADB5')
  if 'screw' in p.label:q.cad_material={'metalness':.98,'roughness':.14}
  parts.append(q)
 return parts


def make_cmc_parent_comb():
 label='thumb_cmc_parent_inlet_comb';hostworld=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss')
 host=bd.Rot(0,0,-45)*bd.Pos(-THUMB_CMC[0],-THUMB_CMC[1],0)*hostworld
 contract=cmc_inlet_contract();points=[r['anchor'] for r in contract];tangent=contract[0]['tangent']
 lower,upper,screws,ears,cutters=_comb(points,tangent,label)
 # A single branching outrigger reaches the actual proximal dorsal rib. The
 # exact rib surface is subtracted from both jaws and the final strut root.
 hl,hu,hb,foot=_host_clamp(host,2.98,-8.,-17.98,-1,label,width=4.,height=4.6)
 hl.label=label+'_palm_rib_lower_cap'
 c=next(e for e in ears if e[0]>0)
 import json
 from pathlib import Path
 controls=json.loads(Path(__file__).with_name('cmc_parent_arm.json').read_text())['controls']
 arm=_sweep([(c[0]+.36,c[1],-.36),*controls,(2.98,-8.,-15.81)],.28)
 lower=lower.fuse(arm-host,hu)
 # Retain the one-piece outrigger while opening the real adjacent wrist liner.
 from lib.neutral_routes import NEUTRAL_ROUTES
 route=next(r for r in NEUTRAL_ROUTES if r['name']=='thumb_cmc_abduction_negative')
 group=next(g for g in route['groups'] if g['label']=='thumb_cmc_abduction_negative_wrist_guide')
 local=bd.Rot(0,0,-45)*bd.Pos(-THUMB_CMC[0],-THUMB_CMC[1],0)
 lower=lower.cut(*[local*_sweep(seg['points'],.49) for seg in group['path'] if seg['kind']=='bezier'])
 return _parts_finish(lower,upper,[hl,hb,*screws],host,cutters,label)


def make_cmc_child_four_comb():
 label='thumb_cmc_child_four_liner_comb';host=_meta_host()
 points=[r['outlet'] for r in cmc_inlet_contract() if 'mcp_flexion' not in r['tendon']]
 lower,upper,screws,ears,cutters=_comb(points,(0,1,0),label)
 extras=[]
 for side in(-1,1):
  hl,hu,hb,foot=_host_clamp(host,side*7.65,12.25,-11.82,side,label+f'_{side:+d}')
  hu.label=label+f'_rail_{side:+d}_cap';extras.extend([hu,hb]);c=next(e for e in ears if np.sign(e[0])==side)
  arm=_sweep([(c[0]+side*.36,12.25,-.36),(side*12.,12.25,-8.),(side*11.5,12.25,-15.),foot],.25)
  lower=lower.fuse(arm-host,hl)
 return _parts_finish(lower,upper,[*extras,*screws],host,cutters,label)


def make_cmc_child_flexion_clamp(sign):
 label='thumb_cmc_child_flexion_'+('positive' if sign>0 else 'negative')+'_clamp';host=_meta_host()
 point=next(r['outlet'] for r in cmc_inlet_contract() if 'mcp_flexion' in r['tendon'] and np.sign(r['lane'])==sign)
 lower,upper,screws,ears,cutters=_comb([point],(0,1,0),label,ear_sides=(-sign,))
 z=12.025 if sign>0 else -14.17
 hl,hu,hb,foot=_host_clamp(host,sign*7.55,16.,z,sign,label)
 structural,cap=(hl,hu) if sign>0 else (hu,hl)
 cap.label=label+('_rail_upper_cap' if sign>0 else '_rail_lower_cap')
 x,_,cz=point;foot=(sign*6.27,16.,z-sign*.85)
 arm=_sweep([(x+sign*.50,16.,cz-.30),(sign*4.2,16.,cz-.30),(sign*6.27,16.,foot[2]-sign*2.),foot],.25)
 lower=lower.fuse(arm-host,structural)
 return _parts_finish(lower,upper,[cap,hb,*screws],host,cutters,label)


def thumb_cmc_mounts():
 base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45);out=[]
 for factory,frame in ((make_cmc_parent_comb,'wrist_flexion'),(make_cmc_child_four_comb,'thumb_cmc_flexion'),(lambda:make_cmc_child_flexion_clamp(-1),'thumb_cmc_flexion'),(lambda:make_cmc_child_flexion_clamp(1),'thumb_cmc_flexion')):
  print('CMC_MOUNT_FACTORY',factory.__name__,frame,flush=True)
  for p in factory():out.append((base*p,frame,'thumb','fastener' if 'screw' in p.label else 'guide_mount'))
 from lib.cmc_parent_clearance import clear_cmc_part
 return [(q,f,s,k) for p,f,s,k in out for q in clear_cmc_part(p)]


def cmc_mount_ownership():
 """Twelve material anchors; the two Y16 clamps also hold the next liners."""
 out=[]
 for r in cmc_inlet_contract():
  suffix='positive' if r['lane']>0 else 'negative'
  child='thumb_cmc_child_flexion_'+suffix+'_clamp' if 'mcp_flexion' in r['tendon'] else 'thumb_cmc_child_four_liner_comb'
  out.extend([{'tendon':r['tendon'],'group':r['tendon']+'_cmc_reaction','end':'inlet','frame':'wrist_flexion','point_local':r['anchor'],'tangent_local':r['tangent'],'mount':'thumb_cmc_parent_inlet_comb'},
              {'tendon':r['tendon'],'group':r['tendon']+'_cmc_reaction','end':'outlet','frame':'thumb_cmc_flexion','point_local':r['outlet'],'tangent_local':r['outlet_tangent'],'mount':child}])
 return out
