"""Exported fingertip systems with their five real distal hosts, for local QA."""
from cadgen import step,read_step,build123d as bd
from lib.native_integration import ROOT,leaves

@step(out='../../STEP/anthropomorphic_hand/tip_export_repair_review.step')
def tip_export_repair_review():
    folder=ROOT/'STEP/anthropomorphic_hand'
    parts=leaves(read_step(folder/'fingertip_pad_export_repair.step'))
    parts+=leaves(read_step(folder/'fingernail_export_repair_review.step'))
    parts += [p for p in leaves(read_step(folder/'phalanx_beauty_review.step')) if p.label.endswith('_distal_frame')]
    assert len(parts)==65
    return bd.Compound(label='repaired_pad_and_nail_systems_with_hosts',children=parts)

if __name__=='__main__':tip_export_repair_review()
