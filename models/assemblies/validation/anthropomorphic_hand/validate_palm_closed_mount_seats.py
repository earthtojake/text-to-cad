from cadgen import build123d as bd,read_step
s=read_step('models/assemblies/STEP/anthropomorphic_hand/palm_frame_candidate_review.step')
for x in(-24,24):
 ring=bd.Pos(x,14,-10.2)*(bd.Cylinder(1.85,3.2)-bd.Cylinder(1.65,4))
 missing=ring-s;v=sum(q.volume for q in missing.solids()) if missing else 0
 print(x,'missing closed annulus volume',v,'bounds',missing.bounding_box() if missing else None,flush=True)
