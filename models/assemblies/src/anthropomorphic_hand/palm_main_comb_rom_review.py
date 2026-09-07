from cadgen import step
from lib.palm_comb_relief import relieved_palm
@step(out='../../STEP/anthropomorphic_hand/palm_main_comb_rom_review.step',mesh_tolerance=.008,mesh_angular_tolerance=.04)
def palm_main_comb_rom_review():return relieved_palm('main')
if __name__=='__main__':palm_main_comb_rom_review()
