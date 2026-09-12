"""Exercise separated, touching, crossing and nested solids plus actual hand contacts."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
from rigid_separation_filter import separation
from check_native_reported_contacts import native_shapes

box=bd.Box(10,10,10)
cases=[('separated',box,bd.Pos(12,0,0)*box,True),('touching',box,bd.Pos(10,0,0)*box,False),('crossing',box,bd.Pos(9,0,0)*box,False),('contained',box,bd.Box(2,2,2),False),('reverse_contained',bd.Box(2,2,2),box,False),('coincident',box,box,False),('separated_in_hole',bd.Cylinder(5,5)-bd.Cylinder(3,6),bd.Cylinder(2,4),True)]
rows=[]
for name,a,b,expected in cases:
    gap=separation(a.wrapped,b.wrapped);assert (gap is not None)==expected,(name,gap)
    rows.append(dict(case=name,conservative_distance_mm=gap,expected_separated=expected,pass_=True))
manifest_file=HERE/'rigid_clearance_inputs.json';manifest=json.loads(manifest_file.read_text())
step=Path(manifest['step']);assert hashlib.sha256(step.read_bytes()).hexdigest()==manifest['step_sha256']
shapes=native_shapes(step)
contacts_file=HERE/'native_contact_regions.json';contacts=json.loads(contacts_file.read_text())['rows']
for row in contacts:
    if not row['native_collision']:continue
    fk=assembled_transforms(row['pose']);relative=np.linalg.inv(fk[row['a_frame']])@fk[row['b_frame']]
    a=shapes[row['a']];b=matrix_location(relative)*shapes[row['b']]
    gap=separation(a.wrapped,b.wrapped)
    assert gap is None,('incorrectly separated native contact',row['a'],row['b'],gap)
    rows.append(dict(a=row['a'],b=row['b'],sample=row['sample'],conservative_distance_mm=gap,expected_separated=False,pass_=True))
result={'pass':True,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),HERE/'rigid_separation_filter.py',manifest_file,step,contacts_file)},'rows':rows}
(HERE/'rigid_separation_filter_check.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS',len(rows),flush=True)
