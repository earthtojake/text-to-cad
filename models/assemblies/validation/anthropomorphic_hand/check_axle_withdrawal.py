import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.axle import make_driven_axle
rows=[]
for radius,flat,length in [(1.,.75,26.),(1.,.75,6.),(3.,2.25,46.)]:
    shaft=make_driven_axle(length,radius,flat)
    circle=bd.Cylinder(radius+.03,length,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    trim=bd.Pos(flat,-radius-1,-1)*bd.Box(radius+1,2*radius+2,length+2,align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    hub=bd.Cylinder(radius+1,length,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))-(circle-trim)
    for i in range(21):
        shift=-length*i/20
        overlap=(hub & (bd.Pos(0,0,shift)*shaft)).volume
        rows.append({'shaft_radius_mm':radius,'shaft_length_mm':length,'withdrawal_mm':shift,'intersection_mm3':overlap,'clear':overlap<1e-8})
Path(__file__).with_suffix('.json').write_text(json.dumps({'scope':'Continuous keyed shaft through complete matching D sleeve at21 withdrawal positions per size','samples':rows},indent=2))
print(len(rows),'withdrawal checks; failures',sum(not r['clear'] for r in rows))
assert all(r['clear'] for r in rows)
