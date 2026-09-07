from cadgen import step
from lib.palm_comb_relief import relieved_palm
@step(out='../../STEP/anthropomorphic_hand/palm_little_comb_rom_review.step',mesh_tolerance=.008,mesh_angular_tolerance=.04)
def palm_little_comb_rom_review():return relieved_palm('little')
if __name__=='__main__':palm_little_comb_rom_review()
