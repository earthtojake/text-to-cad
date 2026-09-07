"""All 336 driven terminal and capstan bond occurrences in the assembled neutral hand fan."""
from cadgen import build123d as bd,step
from lib.drive_terminal import drive_terminal_bodies,capstan_bond_bodies

@step(out='../../STEP/anthropomorphic_hand/drive_terminal_placements.step',mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def drive_terminal_placements():
    return bd.Compound(label='all_48_driven_tendon_terminal_assemblies',children=[s for s,*_ in drive_terminal_bodies()+capstan_bond_bodies()])

if __name__=='__main__':drive_terminal_placements()
