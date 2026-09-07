"""Fixed palm-side guide bank for the index ray."""
from pathlib import Path
from cadgen import build123d as bd,read_step,step
from lib.palm_guide_mounts import make_palm_ray_mounts

@step(out='../../STEP/anthropomorphic_hand/index_palm_guide_mounts.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def index_palm_guide_mounts():
    from lib.palm_frame import make_palm_frame_bodies
    host=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss')
    return bd.Compound(label='index_palm_guide_bank',children=[p[0] for p in make_palm_ray_mounts('index',host)])

if __name__=='__main__':index_palm_guide_mounts()
