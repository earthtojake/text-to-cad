from cadgen import step
from lib.phalanx_continuous_r5 import make_phalanx
@step(out="../STEP/phalanx_continuous_r5.step")
def phalanx_continuous_r5():return make_phalanx(45,18,label="middle_proximal_frame")
if __name__=="__main__":phalanx_continuous_r5()
