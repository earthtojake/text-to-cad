"""Protected bearing, mount and comb-seat envelopes used by palm repairs."""
from cadgen import build123d as bd
from lib.layout import MCP_PALM_SUPPORT_PLANES,CMC_PALM_SUPPORT_PLANES
from lib.palm_frame import PALM_MOUNT_CENTERS,PALM_PAD_MOUNTS

def seating_zones():
    zones=[]
    for x,y in ((-36,101),(-12,105),(12,100),(-35,36)):
        for z in CMC_PALM_SUPPORT_PLANES if x==-35 else MCP_PALM_SUPPORT_PLANES:
            zones.append((f'bearing_{x}_{y}_{z}',bd.Pos(x,y,z)*bd.Cylinder(4.2,2.2)))
    for i,c in enumerate(PALM_MOUNT_CENTERS):zones.append((f'wrist_mount_{i}',bd.Pos(*c)*bd.Cylinder(3.35,3.3)))
    for i,c in enumerate(PALM_PAD_MOUNTS):zones.append((f'pad_mount_{i}',bd.Pos(*c)*bd.Cylinder(2.55,2.3)))
    for y in (35.,75.):zones.append((f'cup_seat_{y}',bd.Pos(22,y,0)*bd.Cylinder(4.2,2.5,rotation=(90,0,0))))
    e=bd.Edge.make_bezier((-35,36,-18),(-32.12,34.92,-18),(-28.7216,34.8768,-18),(-25.457984,35.543808,-18))
    zones.append(('cmc_parent_comb_seating_rail',bd.sweep(bd.Plane(origin=e.position_at(0),z_dir=e.tangent_at(0))*bd.Circle(1.3),path=e)))
    return zones
