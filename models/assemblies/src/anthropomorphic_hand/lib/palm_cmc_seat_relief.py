"""Lower positive CMC support with a continuous open rib through checked motion envelopes."""
import json
from pathlib import Path
from cadgen import build123d as bd,read_step
from .palm_frame_paths import PALM_PATHS
from .transport_guide import path_wire
from .finish import finish

def swept(segments,r):
    w=path_wire([{'kind':'bezier','points':p} for p in segments])
    return bd.sweep(bd.Plane(origin=w.position_at(0),z_dir=w.tangent_at(0))*bd.Circle(r),path=w,is_frenet=True)

def make_final_main():
    base=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand'
    shape=read_step(base/'palm_main_comb_rom_review.step')
    old=next(r for r in PALM_PATHS if r['name']=='thumb_14_bearing_branch')['segments'][7:]
    obsolete=swept(old,1.43)
    obsolete=obsolete.fuse(bd.Pos(-35,36,14)*bd.Cylinder(4.4,3.2))
    shape=shape-obsolete
    data=json.loads(Path(__file__).with_name('palm_cmc_connection_path.json').read_text())
    rib=swept(data['segments'],data['radius'])
    rib=rib.fuse(bd.Pos(*data['segments'][0][0])*bd.Sphere(.95))
    seat=bd.Pos(-35,36,9.3)*bd.Cylinder(1.85,1.4)
    shape=shape.fuse(rib,seat)
    shape=shape-(bd.Pos(-35,36,9.3)*bd.Cylinder(1.58,3.4))
    solids=sorted(shape.solids(),key=lambda s:s.volume,reverse=True)
    print('CMC SOLIDS',[s.volume for s in solids],flush=True)
    if sum(s.volume for s in solids[1:])>1:raise ValueError('detached old CMC branch fragments')
    shape=solids[0]
    bands=[bd.Pos(x,y,12.5)*(bd.Cylinder(2.3,2)-bd.Cylinder(1.83,3)) for x,y in[(-36,101),(-12,105),(12,100)]]
    bands.append(bd.Pos(-35,36,9.3)*(bd.Cylinder(1.85,1.4)-bd.Cylinder(1.58,3)))
    for band in bands:
        missing=band-shape
        if missing and sum(s.volume for s in missing.solids())>1e-6:raise ValueError('bearing seat not completely connected')
    if not shape.is_valid or len(shape.solids())!=1:raise ValueError('invalid final CMC palm')
    return finish(shape,'aluminum','palm_metacarpal_truss')
