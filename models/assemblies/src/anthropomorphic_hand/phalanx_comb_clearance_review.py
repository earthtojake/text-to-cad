"""Native revision of the MCP center opening, preserving all guide mouth datums."""
import json,hashlib
from pathlib import Path
from cadgen import build123d as bd,read_step,step
from lib.layout import FINGERS,finger_fan_matrix
from lib.assembly import matrix_location
from lib.native_integration import leaves,appearance
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'STEP/anthropomorphic_hand/imported/phalanx_guide_mounts_pre_clearance.step'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='6995c4c7521451a2e284e9c5c31d582a7a088d6f7f03d3cc2e2cd938c37b1258'

@step(out='../../STEP/anthropomorphic_hand/phalanx_comb_clearance_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.015)
def phalanx_comb_clearance_review():
    original=leaves(read_step(SOURCE));out=[];records=[];changes=[]
    styles=json.loads((ROOT/'validation/anthropomorphic_hand/integration_native_base_appearance.json').read_text())['occurrences']
    for shape in original:
        name=shape.label;f=next(f for f in FINGERS if name.startswith(f.name+'_'))
        pieces=[shape]
        if '_mcp_outlet_comb_' in name and ('structural_lower_jaw_1' in name or 'scalloped_upper_jaw' in name):
            placement=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)
            cutter=placement*bd.Pos(0,12.25,0)*bd.Box(5,4,6)
            result=shape-cutter;pieces=list(result.solids())
            changes.append({'original':name,'original_volume':shape.volume,'revised_volume':sum(s.volume for s in pieces),'pieces':len(pieces)})
        for i,s in enumerate(pieces):
            s.label=name if len(pieces)==1 else name+'_lateral_'+str(i+1)
            appearance(s,styles[name]);assert s.is_valid and len(s.solids())==1
            frame=f.name+('_pip' if '_pip_outlet_' in name else '_mcp_flexion')
            out.append(s);records.append({'name':s.label,'frame':frame,'system':f.name,'kind':'guide_mount'})
    (ROOT/'validation/anthropomorphic_hand/phalanx_comb_clearance_frames.json').write_text(json.dumps(records,indent=2)+'\n')
    (ROOT/'validation/anthropomorphic_hand/phalanx_comb_clearance_changes.json').write_text(json.dumps(changes,indent=2)+'\n')
    return bd.Compound(label='phalanx_reaction_comb_clearance',children=out)

if __name__=='__main__':phalanx_comb_clearance_review()
