"""The15 real phalanges; four verified arch removals,11 frozen originals."""
from pathlib import Path
from cadgen import build123d as bd,step,read_step
from lib.layout import FINGERS,finger_fan_matrix
from lib.assembly import matrix_location
from lib.finish import finish
BASE=Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand'
REFINED={'middle_proximal_frame','middle_middle_frame','ring_middle_frame','little_proximal_frame'}
NAMES={f.name+'_'+r+'_frame' for f in FINGERS for r in ('proximal','middle','distal')}|{'thumb_metacarpal_frame','thumb_proximal_frame','thumb_distal_frame'}
def leaves(s):return [x for c in s.children for x in leaves(c)] if s.children else [s]
def base_bodies():return leaves(read_step(BASE/'imported/integration_native_base.step'))
def replacements():
    out={}
    for f in FINGERS:
        for i,role in enumerate(('proximal','middle','distal')):
            name=f.name+'_'+role+'_frame'
            if name not in REFINED:continue
            s=read_step(BASE/'phalanx_beauty_native'/(name+'.step'))
            s=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y+sum(f.lengths[:i]),0)*s
            out[name]=finish(s,'aluminum',name)
    assert len(out)==4
    return out
def refined_phalanges():
    repl=replacements();old=[s for s in base_bodies() if s.label in NAMES]
    assert len(old)==15
    return [repl.get(s.label,s) for s in old]
@step(out='../../STEP/anthropomorphic_hand/phalanx_beauty_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.018)
def phalanx_beauty_review():return bd.Compound(label='refined_phalanges_at_actual_assembled_datums',children=refined_phalanges())
if __name__=='__main__':phalanx_beauty_review()
