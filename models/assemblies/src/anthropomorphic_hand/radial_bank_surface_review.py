"""Unchanged native bank geometry for corrected surface-export verification."""
from cadgen import step,build123d as bd
from lib.native_integration import ROOT
from hand_mechanical_candidate import native_parts

@step(out='../../STEP/anthropomorphic_hand/radial_bank_surface_review.step')
def radial_bank_surface_review():
    parts=native_parts(ROOT/'STEP/anthropomorphic_hand/radial_bank_screw_clearance_candidate.step')
    assert len(parts)==1
    return bd.Compound(label='radial_bank_surface_export_review',children=list(parts.values()))

if __name__=='__main__':radial_bank_surface_review()
