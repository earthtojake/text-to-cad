"""Piecewise CMC reaction arm preserving mouth, clamp and endpoint tangents."""
from cadgen import build123d as bd
from lib.yaw_guide_mounts import _mouth,_hub_clamp,_finish,make_yaw_reaction_mounts
from lib.universal_carrier import make_universal_carrier

def make_piecewise_candidate(paths):
    from lib.phalanx_r5_boolean import cut
    name='thumb_cmc_negative_yaw_outlet';delta=1.5
    host=make_universal_carrier(phalanx_width=19.,yaw_plane=9.5)
    mouth,cap,screw=_mouth(1,'thumb_cmc_positive_yaw_outlet')
    mouth=bd.Pos(0,0,-delta)*bd.Rot(0,180,0)*mouth
    screw=bd.Pos(0,0,-delta)*bd.Rot(0,180,0)*screw
    hub,hubcap,bolts=_hub_clamp(host,-1,name+'_hub_clamp',delta);hub,hubcap=hubcap,hub
    wire=bd.Wire([bd.Edge.make_bezier(*points) for points in paths])
    arm=bd.sweep(bd.Plane(origin=paths[0][0],z_dir=wire.tangent_at(0))*bd.Circle(.24),path=wire)
    body=mouth.fuse(hub,arm)-host
    body=body-(bd.Pos(-.9,-3.275,-7.95)*bd.Cylinder(.22,3,rotation=(0,90,0)))
    for y in (-3.5,3.5):body=body-(bd.Pos(0,y,-15.2)*bd.Cylinder(.32,3,rotation=(0,90,0)))
    for mate in [screw,*bolts]:body=body-mate
    solids=sorted(body.solids(),key=lambda s:s.volume,reverse=True);assert len(solids)==2
    baseline=make_yaw_reaction_mounts(19,'thumb_cmc',7.,9.5,negative_bow_y=-12.)
    retained=next(s for s in baseline if s.label==name+'_structural_jaw_2')
    assert not cut(solids[1],retained).faces() and not cut(retained,solids[1]).faces(),'candidate altered the separately retained clamp segment'
    result=solids[0];assert result.is_valid and result.volume>0
    return _finish(result,name+'_structural_jaw_1')
