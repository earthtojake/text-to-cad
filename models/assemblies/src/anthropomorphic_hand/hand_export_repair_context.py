"""Pad/nail export and thumb-arm candidates in the complete hand, for visual QA."""
import json
from cadgen import step
from lib.native_integration import integrated_native_bodies,overlay,ROOT
from lib.assembly import compound

@step(out='../../STEP/anthropomorphic_hand/hand_export_repair_context.step')
def hand_export_repair_context():
    bodies=integrated_native_bodies();folder=ROOT/'STEP/anthropomorphic_hand';reports=ROOT/'validation/anthropomorphic_hand'
    pads=json.loads((reports/'fingertip_pad_export_repair_frames.json').read_text())
    bodies=overlay(bodies,folder/'fingertip_pad_export_repair.step',pads,replace=True)
    nails=json.loads((reports/'fingernail_export_repair_frames.json').read_text())
    bodies=overlay(bodies,folder/'fingernail_export_repair_review.step',nails,replace=True)
    jaw=[dict(name='thumb_cmc_negative_yaw_outlet_structural_jaw_1',frame='thumb_cmc_abduction',system='thumb',kind='guide_mount')]
    bodies=overlay(bodies,folder/'thumb_cmc_negative_jaw_repair_review.step',jaw,replace=True)
    assert len(bodies)==3257
    return compound(bodies,'export_repair_in_complete_hand')

if __name__=='__main__':hand_export_repair_context()
