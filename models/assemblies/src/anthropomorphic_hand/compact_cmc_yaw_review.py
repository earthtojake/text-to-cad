import json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.compact_cmc_yaw import compact_cmc_hardware
@step(out='../../STEP/anthropomorphic_hand/compact_cmc_yaw_review.step',mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def compact_cmc_yaw_review():
 bodies=compact_cmc_hardware()
 Path('models/assemblies/validation/anthropomorphic_hand/compact_cmc_yaw_frames.json').write_text(json.dumps([dict(name=p.label,frame=f,system=s,kind=k) for p,f,s,k in bodies],indent=2)+'\n')
 return bd.Compound(children=[p for p,*_ in bodies],label='compact_CMC_positive_bearing_stack')
if __name__=='__main__':compact_cmc_yaw_review()
