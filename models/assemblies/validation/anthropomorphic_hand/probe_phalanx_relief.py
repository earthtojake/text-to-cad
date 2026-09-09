import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.phalanx import make_phalanx
s=make_phalanx(45,18)
# Remove medial windows between guide/arch stations, preserving 1.4-mm seat bands.
for yc,halfspan in [(8.3,2.8),(21.9,4.3),(35.6,1.1)]:
    cutter=bd.Plane(origin=(0,yc,0),x_dir=(0,1,0),z_dir=(1,0,0))*bd.Ellipse(halfspan,3.85)
    cutter=bd.extrude(cutter,amount=22,both=True)
    before=s
    s=s-cutter
    print(yc,s.is_valid,len(s.solids()),before.volume-s.volume,flush=True)
    ee=[e for e in s.edges() if e.geom_type==bd.GeomType.ELLIPSE]
    print('edges',[(e.length,tuple(e.center())) for e in ee],flush=True)
    try:s=bd.fillet(ee,.08); print('fillet',s.is_valid,flush=True)
    except Exception as e:print('fail',str(e),flush=True)
bd.export_step(s,'models/assemblies/STEP/anthropomorphic_hand/phalanx_relief_probe.step')
