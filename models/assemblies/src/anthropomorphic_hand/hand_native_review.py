"""Native integration checkpoint; final acceptance gates remain independent."""
from cadgen import step
from lib.native_integration import integrated_native_bodies,ROOT
from lib.assembly import compound
import json

@step(out='../../STEP/anthropomorphic_hand/hand_native_review.step')
def hand_native_review():
    bodies=integrated_native_bodies()
    (ROOT/'validation/anthropomorphic_hand/hand_native_body_frames.json').write_text(json.dumps([
        {'name':b.name,'frame':b.frame,'system':b.system,'kind':b.kind} for b in bodies],indent=2)+'\n')
    return compound(bodies,'anthropomorphic_tendon_hand')

if __name__=='__main__':hand_native_review()
