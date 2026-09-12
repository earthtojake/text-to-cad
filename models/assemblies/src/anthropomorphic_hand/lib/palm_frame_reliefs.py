"""Smooth local rim relief around fixed liners, retaining complete bolt seats."""
from cadgen import build123d as bd
from .transport_guide import path_wire
from .neutral_routes import NEUTRAL_ROUTES

def _tube(path,r=.65):
    wire=path_wire(path)
    section=bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(r)
    return bd.sweep(section,path=wire)

def relieve_frame(s):
    path=next(g['path'] for r in NEUTRAL_ROUTES for g in r['groups'] if g['label']=='thumb_mcp_flexion_positive_cmc_reaction')
    s=s-(_tube(path) & (bd.Pos(-35,36,14)*bd.Box(11,11,4)))
    from .palm_current_relief_paths import PALM_PAD_RELIEF_PATHS,PALM_FOOT_55_RELIEF_PATH
    # Three smooth limiting wrist poses reserve the intervening route field.
    # An intact radius 1.2 seat surrounds the radius .8 pad fastener bore.
    protect=bd.Pos(-24,55,11.5)*bd.Cylinder(1.2,2.2)
    region=bd.Pos(-24,55,11.5)*bd.Box(9,9,7)
    for path in PALM_PAD_RELIEF_PATHS:
        cutter=(_tube(path,.81) & region)-protect
        if cutter:s=s-cutter
    from .palm_foot_relief_paths import PALM_FOOT_RELIEF_PATHS
    for path in [*PALM_FOOT_RELIEF_PATHS,PALM_FOOT_55_RELIEF_PATH]:
        cutter=(_tube(path) & (bd.Pos(-24,14,-10.2)*bd.Box(8,8,4)))-(bd.Pos(-24,14,-10.2)*bd.Cylinder(1.85,3.2))
        if cutter:s=s-cutter
    return s
