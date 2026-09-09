import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.phalanx import make_phalanx
s=make_phalanx(45,18)
lo,hi=16.,27.4;mid=(lo+hi)/2;span=hi-lo;xo=9.01;xi=8.56
edges=[bd.Edge.make_bezier((xo,lo,0),(xo,lo+.22*span,0),(xi,mid-.18*span,0),(xi,mid,0)),bd.Edge.make_bezier((xi,mid,0),(xi,mid+.18*span,0),(xo,hi-.22*span,0),(xo,hi,0)),bd.Edge.make_line((xo,hi,0),(12,hi,0)),bd.Edge.make_line((12,hi,0),(12,lo,0)),bd.Edge.make_line((12,lo,0),(xo,lo,0))]
c=bd.extrude(bd.Face(bd.Wire(edges)),amount=14,both=True)
s=s-c-bd.mirror(c,bd.Plane.YZ)
print('cut',s.is_valid,len(s.solids()),s.volume,flush=True)
es=[e for e in s.edges() if e.bounding_box().min.Y>lo and e.bounding_box().max.Y<hi and e.bounding_box().size.X>.02]
print('edges',[(e.geom_type,e.length,tuple(e.center())) for e in es],flush=True)
try:s=bd.fillet(es,.08);print('fillet',s.is_valid,len(s.solids()),flush=True)
except Exception as e:print('filletfail',str(e),flush=True)
bd.export_step(s,'models/assemblies/STEP/anthropomorphic_hand/phalanx_waist_probe.step')
