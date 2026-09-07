from cadgen import step
from lib.palm_cmc_seat_relief import make_final_main
@step(out='../../STEP/anthropomorphic_hand/palm_main_final_rom_review.step',mesh_tolerance=.008,mesh_angular_tolerance=.04)
def palm_main_final_rom_review():return make_final_main()
if __name__=='__main__':palm_main_final_rom_review()
