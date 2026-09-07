import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.phalanx import make_phalanx
s=bd.import_step("models/assemblies/STEP/anthropomorphic_hand/phalanx_waist_probe.step")
original=s
lo,hi=16.,27.4
print('cut',s.is_valid,len(s.solids()),s.volume,flush=True)
es=[e for e in s.edges() if e.bounding_box().min.Y>lo and e.bounding_box().max.Y<hi and e.bounding_box().size.X>.02]
print('edges',[(e.geom_type,e.length,tuple(e.center())) for e in es],flush=True)
try:s=bd.fillet(es,.02);print('fillet',s.is_valid,len(s.solids()),flush=True)
except Exception as e:print('filletfail',str(e),flush=True)
bd.export_step(s,'models/assemblies/STEP/anthropomorphic_hand/phalanx_waist_blend_probe.step')
