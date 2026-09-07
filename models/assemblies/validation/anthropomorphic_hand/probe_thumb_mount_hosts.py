import sys
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd
from lib.palm_frame import make_palm_frame_bodies
from lib.thumb_metacarpal import make_thumb_metacarpal
parts=make_palm_frame_bodies();print([(p.label,p.volume) for p in parts],flush=True)
host=next(p for p in parts if p.label=='palm_metacarpal_truss');host=bd.Rot(0,0,-45)*bd.Pos(35,-36,0)*host
for y in(-12.,-16.,-20.):
 s=host & (bd.Pos(6,y,14)*bd.Box(22,.05,6));print('parent',y,[(b.bounding_box().min.to_tuple(),b.bounding_box().max.to_tuple()) for b in s.solids()],flush=True)
host=make_thumb_metacarpal()
for y in(12.25,16.):
 for z in(-10.,10.):
  s=host&(bd.Pos(7.5,y,z)*bd.Box(4,.05,10));print('child',y,z,[(b.bounding_box().min.to_tuple(),b.bounding_box().max.to_tuple()) for b in s.solids()],flush=True)
