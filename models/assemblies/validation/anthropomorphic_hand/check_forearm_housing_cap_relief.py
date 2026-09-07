"""Actual transverse-brace clearance during the two corrected cap removals."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
HERE=Path(__file__).resolve().parent
def leaves(n):return [s for c in n.children for s in leaves(c)] if n.children else [n]
parts=leaves(read_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_housing_review.step'))
brace=bd.Pos(0,-67.5,0)*bd.fillet(bd.Box(76,2.25,3.4).edges(),1.0)
rows=[]
for side in ('left','right'):
    sign=-1 if side=='left' else 1
    cap=next(s for s in parts if s.label==side+'_forearm_rail_clamp_2_removable_cap')
    for i in range(21):
        common=(bd.Pos(-sign*i*.05,0,0)*cap)&brace
        rows.append({'body':cap.label,'travel_mm':i*.05,'overlap':0. if common is None else common.volume})
report={'ok':all(r['overlap']<1e-7 for r in rows),'removal_samples':rows,'scope':'Corrected caps against actual rounded transverse brace. Previous screw seats and cap/rail removals remain valid because the cap correction only removes an inward-open mid-height window.'}
(HERE/'forearm_housing_cap_relief.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'ok':report['ok'],'samples':len(rows)}))
sys.exit(0 if report['ok'] else 1)
