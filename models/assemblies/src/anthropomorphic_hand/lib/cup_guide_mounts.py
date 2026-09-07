"""The fifth ray's ten moving and eight fixed liner-mouth supports."""
from collections import defaultdict
import numpy as np
from cadgen import build123d as bd,read_step
from lib.guide_mounts import guide_end_registry,_finish,_rod,_sweep
from lib.palm_guide_mounts import _row,_boss_clamp
from lib.thumb_cmc_mounts import _comb,_host_clamp
from lib.palm_frame import make_little_metacarpal,make_palm_frame_bodies
from lib.layout import FINGERS,finger_fan_matrix
from lib.finish import finish
import json
from pathlib import Path
PLANS=json.loads(Path(__file__).with_name('remaining_support_paths.json').read_text())


def _cup_host():
 host=read_step(Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/palm_little_review.step')
 while host.children:
  if len(host.children)!=1:raise ValueError('Expected one frozen fifth-ray host')
  host=host.children[0]
 return host


def _real_parts(shape,label):
 from OCP.ShapeFix import ShapeFix_Solid
 from cadgen.validity import _signed_volume
 out=[]
 for i,s in enumerate(shape.solids()):
  repair=ShapeFix_Solid(s.wrapped);repair.Perform();s=bd.Solid(repair.Solid())
  if _signed_volume(s.wrapped)<0:s=bd.Solid(s.wrapped.Reversed())
  out.append(_finish(s,label+('_'+str(i+1) if len(shape.solids())>1 else '')))
 return out


def make_cup_child_bank():
 from lib.assembly import matrix_location
 f=next(f for f in FINGERS if f.name=='little');world=finger_fan_matrix(f).copy();world=world@np.array([[1,0,0,f.x],[0,1,0,f.base_y],[0,0,1,0],[0,0,0,1]])
 inv=np.linalg.inv(world);host=matrix_location(inv)*_cup_host();grouped=defaultdict(list)
 ends=[e for e in guide_end_registry() if e.frame=='palm_cup']
 assert len(ends)==10
 for e in ends:
  p=inv@np.array([*e.point,1]);t=inv[:3,:3]@np.array(e.tangent)
  assert np.linalg.norm(t-[0,1,0])<1e-6
  grouped[(round(p[1],7),round(p[2],7))].append(round(p[0],7))
 backbone=[];caps=[];screws=[];cutters=[];ymin=min(y for y,z in grouped);zmin=min(z for y,z in grouped)-1.35
 plan=json.loads(Path(__file__).with_name('cup_host_anchor.json').read_text())
 hl,hu,hb,foot=_host_clamp(host,*plan['anchor'],plan['side'],'little_cup_child_bank_rib',width=3.8,height=4.)
 hu.label='little_cup_child_bank_rib_cap'
 direct=json.loads(Path(__file__).with_name('cup_child_direct_paths.json').read_text());node=direct['node']
 backbone.extend([bd.Pos(*node)*bd.Sphere(.44),_rod(node,foot,.30)])
 for i,((y,z),xs) in enumerate(sorted(grouped.items())):
  label=f'little_cup_child_bank_row_{i+1:02d}';lower,cap,bolts,roots=_row(xs,y,z,label)
  backbone.append(lower);caps.append(cap);screws.extend(bolts)
  for sign,p in roots:
   backbone.append(_sweep([p,*direct['branches']['child_'+str(i+1)+'_'+str(sign)]['controls'],node],.24))
  cutters.extend(bd.Pos(x,y,z)*bd.Cylinder(.47,2,rotation=(90,0,0)) for x in xs)
 backbone.append(hl);caps.append(hu);screws.append(hb)
 raw=[s for p in backbone for s in p.solids()];fused=raw[0]
 for i,piece in enumerate(raw[1:],1):
  fused=fused.fuse(piece,tol=1e-6)
  if not len(fused.solids()):raise ValueError(('cup child fusion',i))
 body=bd.Part(bd.Compound(children=list(fused.solids())).wrapped).cut(*cutters,*caps,*screws)-host
 parts=_real_parts(body,'little_cup_child_bank_structural')+[_finish(c-host,c.label) for c in caps]+screws
 for p in parts:
  if 'screw' in p.label:finish(p,'steel',p.label)
 return [(matrix_location(world)*p,'palm_cup','little','fastener' if 'screw' in p.label else 'guide_mount') for p in parts]


def make_cup_parent_bank():
 host=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss');grouped=defaultdict(list)
 ends=[e for e in guide_end_registry() if e.frame=='wrist_flexion' and all(r.startswith('little_') for r in e.routes)]
 assert len(ends)==8
 for e in ends:grouped[(round(e.point[1],7),round(e.point[2],7))].append(e.point)
 plan=json.loads(Path(__file__).with_name('cup_fixed_direct_paths.json').read_text())
 branches={-1:[]};caps=[];screws=[];cutters=[];feet={}
 for sign in(-1,):
  x,y,z=plan['anchor']
  hl,hu,hb,foot=_host_clamp(host,x,y,z,1,'little_cup_fixed_bank_'+str(sign),width=3.6,height=3.2)
  hu.label='little_cup_fixed_bank_'+str(sign)+'_palm_rib_cap'
  node=np.array(foot)+[2.4,0,0]
  branches[sign].extend([hl,_rod(foot,node,.30),bd.Pos(*node)*bd.Sphere(.42)])
  caps.append(hu);screws.append(hb);feet[sign]=node
 for i,((y,z),points) in enumerate(sorted(grouped.items())):
  label=f'little_cup_fixed_bank_row_{i+1:02d}';side=-1 if max(p[0] for p in points)>30 else 1
  offset=sum(p[0] for p in points)/len(points)
  lower,cap,bolts,ears,holes=_comb([(p[0]-offset,p[1],p[2]) for p in points],(0,1,0),label,ear_sides=(side,))
  place=bd.Pos(offset,0,0);lower=place*lower;cap=place*cap
  cap.label=label+'_liner_cap'
  bolts=[place*p for p in bolts];holes=[place*p for p in holes];ears=[(p[0]+offset,p[1],p[2]) for p in ears]
  if z>0:
   c=ears[0];flip=bd.Pos(*c)*bd.Rot(180,0,0)*bd.Pos(*(-np.asarray(c)))
   bolts=[_finish((flip*p) & (bd.Pos(c[0],c[1],z-4.56)*bd.Box(4,4,10)),p.label) for p in bolts]
  sign=-1;foot=feet[sign];c=ears[0];start=(c[0]+side*.30,c[1],c[2]-.36)
  start=np.array(start);foot=np.array(foot);delta=foot-start
  arm=_sweep([start,*plan['branches']['parent_'+str(i+1)]['controls'],foot],.26)
  branches[sign].extend([lower,arm]);caps.append(cap);screws.extend(bolts);cutters.extend(holes)
 bodies=[]
 for sign,items in branches.items():
  raw=[]
  for item in items:raw.extend(item.solids())
  fused=raw[0]
  for index,piece in enumerate(raw[1:],1):
   fused=fused.fuse(piece)
   if not len(fused.solids()):raise ValueError(('cup bank fusion',sign,index))
  body=bd.Part(bd.Compound(children=list(fused.solids())).wrapped)-host
  body=body.cut(*cutters,*caps,*screws)
  bodies.extend(_real_parts(body,'little_cup_fixed_bank_'+str(sign)+'_structural'))
 out=[]
 from lib.remaining_cap_relief import clear_cap
 caps=[part for cap in caps for p in _real_parts(cap-host,cap.label) for part in clear_cap(p)]
 for p in [*bodies,*caps,*screws]:
  if 'screw' in p.label:finish(p,'steel',p.label)
  out.append((p,'wrist_flexion','palm','fastener' if 'screw' in p.label else 'guide_mount'))
 return out


def cup_guide_mounts():return make_cup_child_bank()+make_cup_parent_bank()
