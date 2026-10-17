"""One connected palm with all225-packet DIP outer-rim reliefs."""
from cadgen import step
from lib.palm_rom_relief import relieved_palm
@step(out='../STEP/palm_main_rom_review.step')
def palm_main_rom_review():return relieved_palm('main')
if __name__=='__main__':palm_main_rom_review()
