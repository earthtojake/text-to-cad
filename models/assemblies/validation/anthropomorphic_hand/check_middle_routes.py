"""Eight full middle-finger paths: continuity, radii, signs and cable clearances."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from lib.finger_routing import middle_finger_routes,endpoint,tangent
from lib.axis_transport import sample_path,segment_length
from lib.bowden_transport import cubic_point
from check_bowden_transport import metrics


def route_metrics(route):
    pts=[];spacing=0.;length=0.;radius=999.
    for s in route['path']:
        if s['kind']=='bezier':
            m=metrics(s['points']);length+=m['length'];radius=min(radius,m['minimum_radius'])
            c=np.array(s['points']);speedbound=3*np.linalg.norm(np.diff(c,axis=0),axis=1).max();n=int(np.ceil(speedbound/.03))
            pts.extend(cubic_point(c,t) for t in np.linspace(0,1,n+1));spacing=max(spacing,speedbound/n)
        else:
            length+=segment_length(s)
            if s['kind']=='arc':radius=min(radius,float(np.linalg.norm(np.array(s['start'])-s['center'])))
            ps,h=sample_path([s],.03);pts.extend(ps);spacing=max(spacing,h)
    gap=max(np.linalg.norm(np.array(endpoint(a,True))-endpoint(b)) for a,b in zip(route['path'],route['path'][1:]))
    terr=max(np.linalg.norm(np.array(tangent(a,True))-tangent(b)) for a,b in zip(route['path'],route['path'][1:]))
    return {'length_mm':length,'minimum_bend_radius_mm':radius,'maximum_join_gap_mm':float(gap),
            'maximum_tangent_error':float(terr),'points':np.array(pts),'spacing':spacing}


if __name__=='__main__':
    routes=middle_finger_routes();ms=[route_metrics(r) for r in routes]
    collisions=[]
    for i,r in enumerate(routes):
        tree=cKDTree(ms[i]['points'])
        for j in range(i+1,len(routes)):
            d=float(tree.query(ms[j]['points'],workers=1)[0].min())
            lower=d-(ms[i]['spacing']+ms[j]['spacing'])/2-.6
            if lower<=0:collisions.append({'a':r['name'],'b':routes[j]['name'],'sampled_centerline_distance_mm':d,'surface_gap_lower_bound_mm':lower})
    rows=[{'tendon':r['name'],**{k:v for k,v in m.items() if k not in ('points','spacing')}} for r,m in zip(routes,ms)]
    result={'rows':rows,'tendon_collisions_or_unresolved_clearance':collisions,'limitations':'Neutral full paths only; no body collisions yet.'}
    Path(__file__).with_name('middle_routes_report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if collisions or any(m['minimum_bend_radius_mm']<3.5-1e-8 or m['maximum_join_gap_mm']>1e-8 or m['maximum_tangent_error']>1e-8 for m in ms):raise SystemExit(1)
