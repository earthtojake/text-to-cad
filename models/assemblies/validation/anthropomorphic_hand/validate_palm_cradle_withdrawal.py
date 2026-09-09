import json
from cadgen import build123d as bd
s=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/palm_cradle_clearance_review.step')
head=bd.Pos(-23.72,0,0)*bd.Rot(0,90,0)*bd.Cylinder(4.8,5)
hit=s&head
result={'head_withdrawal_gap_mm':s.distance_to(head),'head_withdrawal_intersection_mm3':sum(x.volume for x in hit.solids()) if hit else 0,'valid':s.is_valid,'solids':len(s.solids()),'relief_inner_limit_x_mm':-21.2}
print(result);json.dump(result,open('models/assemblies/validation/anthropomorphic_hand/palm_cradle_withdrawal.json','w'),indent=2)
