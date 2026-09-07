"""Native repaired fingertip bridges with all pad, nail and distal host bodies."""
from cadgen import step,build123d as bd
from lib.native_integration import ROOT,leaves
from hand_mechanical_candidate import native_parts

@step(out='../../STEP/anthropomorphic_hand/tip_bridge_repair_context.step')
def tip_bridge_repair_context():
    folder=ROOT/'STEP/anthropomorphic_hand'
    parts=native_parts(folder/'fingertip_pad_export_repair.step')
    parts.update(native_parts(folder/'fingertip_bridge_repair_review.step'))
    parts.update(native_parts(folder/'fingernail_export_repair_review.step'))
    parts.update({n:p for n,p in native_parts(folder/'phalanx_beauty_review.step').items() if n.endswith('_distal_frame')})
    assert len(parts)==65
    return bd.Compound(label='native_repaired_fingertips_with_hosts',children=list(parts.values()))

if __name__=='__main__':tip_bridge_repair_context()
