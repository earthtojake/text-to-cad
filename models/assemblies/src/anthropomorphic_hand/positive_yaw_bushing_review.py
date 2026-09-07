"""Four turned positive MCP bushings, preserving every shaft and route datum."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.layout import FINGERS,JOINT_BY_NAME
from lib.bushing import make_bushing
from lib.assembly import joint_location

@step(out='../../STEP/anthropomorphic_hand/positive_yaw_bushing_review.step',mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def positive_yaw_bushing_review():
 parts=[];frames=[]
 for f in FINGERS:
  j=JOINT_BY_NAME[f.name+'_mcp_abduction'];name=j.name+'_positive_bushing'
  p=joint_location(j)*bd.Pos(0,0,11.5)*make_bushing(outer_radius=1.8,bore_radius=1.03,length=2.,flange_radius=2.02,label=name)
  p.label=name;parts.append(bd.Compound(children=[p],label=name));frames.append(dict(name=name,frame=j.parent,system=j.system,kind='bushing'))
 Path('models/assemblies/validation/anthropomorphic_hand/positive_yaw_bushing_frames.json').write_text(json.dumps(frames,indent=2)+'\n')
 return bd.Compound(children=parts,label='slender_positive_yaw_bushing_family')
if __name__=='__main__':positive_yaw_bushing_review()
