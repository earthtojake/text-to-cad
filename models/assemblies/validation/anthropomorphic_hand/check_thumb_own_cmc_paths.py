"""Own CMC antagonist paths versus actual carrier, metacarpal and drive drums."""
import json,sys
from math import radians,cos,sin
from pathlib import Path
import numpy as np
from cadgen import build123d as bd
from OCP.gp import gp_Trsf
from lib.thumb_yaw_transport import thumb_yaw_reaction_span
from lib.finger_routing import line,transform_path
from lib.transport_guide import path_wire
from lib.path_analysis import path_min_radius,path_length,sample_path
from lib.universal_carrier import make_universal_carrier
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.pulley import make_pulley
from check_middle_hardware_paths import bbox_gap
from scipy.spatial import cKDTree


def rot(axis,q):
    a=radians(q);c,s=cos(a),sin(a);m=np.eye(4)
    m[:3,:3]=[[1,0,0],[0,c,-s],[0,s,c]] if axis=='x' else [[c,-s,0],[s,c,0],[0,0,1]]
    return m

def location(m):
    t=gp_Trsf();t.SetValues(*m[:3,:].ravel().tolist());return bd.Location(t)

def arc(axis,radius,sign,q,plane):
    return {'kind':'arc','center':[sign*.9,0,0] if axis=='flex' else [0,0,plane],
        'start':[sign*.9,0,sign*radius] if axis=='flex' else [-sign*radius,0,plane],
        'axis':[1,0,0] if axis=='flex' else [0,0,1],'sweepDeg':-sign*150+q}

if __name__=='__main__':
    carrier=make_universal_carrier(phalanx_width=19,yaw_plane=9.5);meta=make_thumb_metacarpal()
    pulley=make_pulley(7.)
    report={'rows':[],'pass':False};out=Path(__file__).with_name('thumb_own_cmc_paths_report.json')
    samples=[(0.,float(q)) for q in (-25,-15,-5,5,15,25,35,45)]+[(float(q),0.) for q in (-15,-5,5,15,25,35,45,55,65)]+[(65.,45.),(-15.,45.),(65.,-25.)]
    if '--neutral-only' in sys.argv:
        samples=[(0.,0.)];out=Path(__file__).with_name('thumb_own_cmc_neutral_report.json')
    else:samples.insert(0,(0.,0.))
    for flex,yaw in samples:
        ry=rot('z',yaw);rf=ry@rot('x',flex)
        bodies=[('carrier',location(ry)*carrier),('metacarpal',location(rf)*meta),('shaft',location(ry)*bd.Cylinder(1,19,rotation=(0,90,0)))]
        for sign in(-1,1):
            bodies.append((f'yaw_{sign}',bd.Pos(0,0,-11 if sign>0 else -13.5)*pulley))
            bodies.append((f'flex_{sign}',location(ry)*bd.Pos(sign*.9,0,0)*bd.Rot(0,90,0)*pulley))
        bounds={n:b.bounding_box() for n,b in bodies};rows=[];routes=[]
        for sign in(-1,1):
            plane=-11 if sign>0 else -13.5
            yawpath=[line([-sign*7,-3,plane],[-sign*7,0,plane]),arc('yaw',7,sign,yaw,plane)]
            span=thumb_yaw_reaction_span(yaw,sign)
            flexgroups=[([line([sign*.9,-24,sign*7],[sign*.9,-23,sign*7])],.3), (span,.45),
                (transform_path([line([sign*.9,-3,sign*7],[sign*.9,0,sign*7]),arc('flex',7,sign,flex,0)],ry),.3)]
            for target,groups in [('yaw',[(yawpath,.3)]),('flex',flexgroups)]:
                paths=[s for path,radius in groups for s in path];routes.append((f'{target}_{sign}',paths))
                for gi,(path,radius) in enumerate(groups):
                    wire=path_wire(path);wb=wire.bounding_box()
                    for name,body in bodies:
                        if bbox_gap(wb,bounds[name])>radius+.1:continue
                        d=wire.distance_to(body)
                        if d<radius-1e-7:rows.append({'tendon':f'{target}_{sign}','group':gi,'solid':name,'centerline_distance_mm':d,'radius':radius})
        clouds=[sample_path(path,.03) for name,path in routes]
        gap=min(float(cKDTree(clouds[i]).query(clouds[j],workers=1)[0].min())-.03-.9 for i in range(4) for j in range(i+1,4))
        row={'flex_deg':flex,'yaw_deg':yaw,'minimum_radius_mm':min(path_min_radius(p) for n,p in routes),'mutual_gap_lower_bound_mm':gap,'collisions':rows}
        row['pass']=bool(not rows and gap>=0 and row['minimum_radius_mm']>=3.5)
        report['rows'].append(row);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
    report['pass']=all(r['pass'] for r in report['rows']);out.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
