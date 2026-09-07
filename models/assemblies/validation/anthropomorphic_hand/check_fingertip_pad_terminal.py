"""Continuous terminal-circle envelope and cross-finger cup route checks."""
import json
from pathlib import Path
from cadgen import build123d as bd
from lib.fingertip_pad import make_fingertip_pad,fingertip_pad_bodies
from lib.layout import FINGERS
from check_fingertip_pads import route_check

root=Path(__file__).parent
report={'pass':False,'terminal_orbits':[],'cup_route_rows':[]}
for name,length,width in [(f.name,f.lengths[2],f.widths[2]) for f in FINGERS]+[('thumb',21.,13.)]:
    for part in make_fingertip_pad(name,length,width):
        gaps=[]
        for sign in (-1,1):
            orbit=bd.Plane(origin=(sign*.9,0,0),x_dir=(0,1,0),z_dir=(1,0,0))*bd.Circle(3.5)
            gaps.append(orbit.wires()[0].distance_to(part)-.3-1e-6)
        report['terminal_orbits'].append({'body':part.label,'clearance_mm':min(gaps),'pass':min(gaps)>0})
    print('terminal',name,'clear',flush=True)
pads=fingertip_pad_bodies()
for q in (0.,10.,20.,25.):
    row=route_check(pads,f'palm_cup_{q:g}',{'palm_cup':q},[f.name for f in FINGERS]+['thumb'])
    report['cup_route_rows'].append(row)
    print('cup',q,row['pass'],row['collisions'],flush=True)
    (root/'fingertip_pad_terminal_report.json').write_text(json.dumps(report,indent=2)+'\n')
report['scope']='Every complete native terminal drive circle at R3.5 and X±0.9 against all six local pad bodies, minus tendon radius0.3: this contains every150-degree terminal arc at every DIP/IP angle. All42 hand routes against all30 assembled pad bodies at cup0/10/20/25deg. Common wrist rigid motion preserves all relative hand-route/pad clearances.'
report['pass']=all(r['pass'] for k in ('terminal_orbits','cup_route_rows') for r in report[k])
(root/'fingertip_pad_terminal_report.json').write_text(json.dumps(report,indent=2)+'\n')
if not report['pass']:raise SystemExit(1)
