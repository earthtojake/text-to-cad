"""Exact tangent-lead clearance against the rotating physical storage capstan."""
import sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.capstan import make_capstan
from lib.layout import TENDONS
from lib.forearm_routing import forearm_route
from lib.transport_guide import path_wire

capstan=make_capstan(); rows=[]
for t in TENDONS[:2]:
    x,y,z=t['capstan_center']; sign=t['sign']
    placement=bd.Pos(x,y,z)*(bd.Rot(0,0,0) if sign==1 else bd.Rot(0,180,0))
    for q in (-5*math.pi,-2.1,0.,1.2,5*math.pi):
        shape=placement*bd.Rot(0,0,math.degrees(q))*capstan
        route=forearm_route(t,q)
        for group in route['groups'][1:3]:
            distance=path_wire(group['path']).distance_to(shape)
            row={'tendon':t['name'],'rotation_rad':q,'group':group['label'],
                 'centerline_distance_mm':distance,'clear':distance>=.30-1e-7}
            rows.append(row);print(row,flush=True)
Path(__file__).with_name('capstan_exit_clearance.json').write_text(json.dumps(rows,indent=2))
assert all(r['clear'] for r in rows)
