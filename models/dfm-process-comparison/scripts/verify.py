"""Check the exported artifacts, not just generator parameters."""
import json
from pathlib import Path
import build123d as bd
ROOT=Path(__file__).resolve().parents[1]
facts={}
for kind in ('baseline','fdm','sheet','cnc'):
    s=bd.import_step(ROOT/'STEP'/f'{kind}.step')
    box=s.bounding_box()
    probe_wall=bd.Pos(35,0,16)*bd.Box(12,2,2)
    probe_floor=bd.Pos(0,0,2)*bd.Box(2,2,6)
    wall=(s & probe_wall).bounding_box().size.X
    floor=(s & probe_floor).bounding_box().size.Z
    circles=[e for e in s.edges() if e.geom_type==bd.GeomType.CIRCLE]
    centers=sorted(set((round(e.arc_center.X,5),round(e.arc_center.Y,5)) for e in circles if abs(e.radius-2.25)<1e-5 and abs(e.arc_center.Z)<1e-5))
    assert centers==[(-25.,-18.),(-25.,18.),(25.,-18.),(25.,18.)]
    assert s.is_valid and len(s.solids())==1
    assert all(abs(a-b)<1e-5 for a,b in zip(box.size,(80,60,25)))
    expected={'baseline':(.8,3),'fdm':(2.4,2.4),'sheet':(1.5,1.5),'cnc':(3,3)}[kind]
    assert abs(wall-expected[0])<1e-5 and abs(floor-expected[1])<1e-5
    radii=sorted(set(round(e.radius,5) for e in circles))
    if kind=='sheet': assert 2.0 in radii and 3.5 in radii
    if kind=='cnc': assert 3.0 in radii
    facts[kind]={'valid':True,'solids':1,'bounds_mm':list(box.size),'volume_mm3':s.volume,'wall_mm':wall,'floor_mm':floor,'circular_edge_radii_mm':radii,'mounting_hole_xy_mm':centers,'hole_diameter_mm':4.5}
(ROOT/'reports'/'geometry-facts.json').write_text(json.dumps(facts,indent=2)+'\n')
print(json.dumps(facts,indent=2))
