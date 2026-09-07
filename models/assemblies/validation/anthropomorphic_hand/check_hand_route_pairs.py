"""Continuous-envelope mutual clearance for all48 assembled hand-side routes."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from lib.hand_routing import hand_side_routes,full_tendon_routes
from lib.path_analysis import sample_path,path_length,path_min_radius
from lib.finger_routing import endpoint,tangent


def group_radius(group):
    return .45 if group.get('guide') in('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .30


def audit(routes,step=.025):
    entries=[];table=[]
    for route in routes:
        path=route['path'];joins=[float(np.linalg.norm(np.asarray(endpoint(a,True))-endpoint(b))) for a,b in zip(path,path[1:])]
        tangents=[float(np.linalg.norm(np.asarray(tangent(a,True))-tangent(b))) for a,b in zip(path,path[1:])]
        table.append({'tendon':route['name'],'length_mm':path_length(path),'minimum_radius_mm':path_min_radius(path),'maximum_join_gap_mm':max(joins,default=0.),'maximum_tangent_error':max(tangents,default=0.)})
        for group in route['groups']:
            points=sample_path(group['path'],step);entries.append((route['name'],group['label'],group_radius(group),points,cKDTree(points),points.min(axis=0),points.max(axis=0)))
    conflicts=[];minimum=999.;tested=0
    for i,(name,group,radius,points,tree,low,high) in enumerate(entries):
        for name2,group2,radius2,points2,tree2,low2,high2 in entries[i+1:]:
            if name==name2:continue
            bound=np.linalg.norm(np.maximum.reduce([low-high2,low2-high,np.zeros(3)]))
            if bound>radius+radius2+.1:continue
            ds,ids=tree.query(points2,workers=1);k=int(np.argmin(ds));gap=float(ds[k])-step-radius-radius2;tested+=1;minimum=min(minimum,gap)
            if gap<0:conflicts.append({'a':name,'group_a':group,'b':name2,'group_b':group2,'gap_lower_bound_mm':gap,'nearest_sample_a':points[ids[k]].tolist(),'nearest_sample_b':points2[k].tolist()})
    return {'scope':'all48 hand-side routes; wrist/forearm prefix excluded','tendon_table':table,'minimum_checked_gap_lower_bound_mm':minimum,'group_pairs_tested':tested,'conflicts':conflicts,'pass':bool(not conflicts and all(r['minimum_radius_mm']>=3.5-1e-10 and r['maximum_join_gap_mm']<1e-8 and r['maximum_tangent_error']<1e-8 for r in table))}

if __name__=='__main__':
    pose=json.loads(next((a for a in sys.argv[1:] if a.startswith('{')),'{}'))
    if '--full' in sys.argv:
        wrist=json.loads(Path(__file__).with_name('wrist_transport_neutral.json').read_text())['routes']
        routes=full_tendon_routes(wrist,pose)
    else:routes=hand_side_routes(pose)
    report=audit(routes);report['pose']=pose
    if '--full' in sys.argv:report['scope']='all48 complete tendons: capstan termination through wrist/hand to driven termination'
    output=Path(__file__).with_name('full_route_pairs_neutral.json' if '--full' in sys.argv else 'hand_route_pairs_neutral.json' if not pose else 'hand_route_pairs_pose.json');output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='tendon_table'},indent=2),flush=True)
    if not report['pass']:raise SystemExit(1)
