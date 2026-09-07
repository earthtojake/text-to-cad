"""Piecewise reaction arm routed outside both CMC drums and all tendon poses."""
import hashlib,json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.thumb_reaction_arm_piecewise import make_piecewise_candidate
from lib.layout import THUMB_CMC
from lib.native_integration import ROOT
from lib.phalanx_r5_boolean import cut
from lib.finish import finish
from hand_mechanical_candidate import native_parts

PATHS = [[[-0.62, -3.275, -7.9], [1.8, -3.275, -7.9], [-1.4239150568688284, 8.075423574700105, -7.9], [-1.4239150568688284, 8.075423574700105, -9.1]], [[-1.4239150568688284, 8.075423574700105, -9.1], [-1.4239150568688284, 8.075423574700105, -11.0333333333333], [-1.4239150568688284, 8.075423574700105, -12.9666666666667], [-1.4239150568688284, 8.075423574700105, -14.9]], [[-1.4239150568688284, 8.075423574700105, -14.9], [-1.4239150568688284, 8.075423574700105, -16.1], [1.8, -3.5, -16.9], [0.4, -3.5, -15.2]]]

@step(out='../../STEP/anthropomorphic_hand/thumb_reaction_arm_clearance_r3.step')
def thumb_reaction_arm_clearance_r3():
    name='thumb_cmc_negative_yaw_outlet_structural_jaw_1';folder=ROOT/'STEP/anthropomorphic_hand'
    oldpath=folder/'thumb_cmc_negative_jaw_repair_review.step';relievedpath=folder/'static_clearance_relief_review.step'
    old=native_parts(oldpath)[name];relieved=native_parts(relievedpath)[name]
    removed=cut(old,relieved);assert removed.solids() and removed.volume>0
    raw=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*make_piecewise_candidate(PATHS)
    shape=cut(raw,removed);assert len(shape.solids())==1 and shape.is_valid and shape.volume>0
    shape=finish(shape.solids()[0],'aluminum',name)
    report=dict(scope=__doc__,paths=PATHS,inherited_machining_mm3=removed.volume,raw_volume_mm3=raw.volume,final_volume_mm3=shape.volume,input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),oldpath,relievedpath)},pass_=True)
    (ROOT/'validation/anthropomorphic_hand/thumb_reaction_arm_clearance_r3_build.json').write_text(json.dumps(report,indent=2)+'\n')
    return bd.Compound(label='context_clearance_reaction_arm_R3',children=[shape])

if __name__=='__main__':thumb_reaction_arm_clearance_r3()
