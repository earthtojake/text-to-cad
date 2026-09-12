import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from lib.phalanx import make_phalanx
s=make_phalanx(45,18); original=s
# Full-width end and guide stations remain untouched. Smooth cubic waist.
for lo,hi in [(4.4,11.45),(13.05,27.45),(34.05,40.6)]:
 mid=(lo+hi)/2; span=hi-lo;xo=9.001;xi=8.13
 edges=[bd.Edge.make_bezier((xo,lo,0),(xo,lo+.22*span,0),(xi,mid-.18*span,0),(xi,mid,0)),bd.Edge.make_bezier((xi,mid,0),(xi,mid+.18*span,0),(xo,hi-.22*span,0),(xo,hi,0)),bd.Edge.make_line((xo,hi,0),(12,hi,0)),bd.Edge.make_line((12,hi,0),(12,lo,0)),bd.Edge.make_line((12,lo,0),(xo,lo,0))]
 c=bd.extrude(bd.Face(bd.Wire(edges)),amount=14,both=True)
 for cut in (c,bd.mirror(c,bd.Plane.YZ)):
  s=s-cut
 print('cut',lo,hi,s.is_valid,len(s.solids()),s.volume,flush=True)
# Round only new long outside boundary curves; leave preserved end-seating faces alone.
es=[e for e in s.edges() if e.geom_type==bd.GeomType.BSPLINE and e.length>1 and e.bounding_box().size.Y>1 and e.bounding_box().size.X>.05 and abs(e.center().X)>7.9]
print('edges',[(e.length,tuple(e.center())) for e in es],flush=True)
for r in [.08,.04,.02]:
 try:
  trial=bd.fillet(es,r);print('fillet',r,trial.is_valid,len(trial.solids()),flush=True);s=trial;break
 except Exception as e:print('fillet failed',r,str(e),flush=True)
bd.export_step(s,'models/assemblies/STEP/anthropomorphic_hand/phalanx_sculpt_probe_r4.step')
print('result',s.is_valid,len(s.solids()),s.volume,flush=True)
# Native difference is a direct test, not a mass-conservation assumption.
op=BRepAlgoAPI_Cut(s.wrapped,original.wrapped);op.Build();new=bd.Shape.cast(op.Shape());print('new-minus-old',len(new.solids()),new.volume,flush=True)
