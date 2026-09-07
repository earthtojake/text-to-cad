"""Full downstream thumb route/body gate from the six CMC outlets."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from cadgen import build123d as bd
from lib.thumb_downstream import thumb_downstream_routes,downstream_transforms
from lib.phalanx import make_phalanx
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.universal_carrier import make_universal_carrier
from lib.pulley import make_pulley
from lib.transport_guide import path_wire
from lib.finger_routing import transform_path
from check_middle_hardware_paths import bbox_gap,rounded_data
from check_middle_routes import route_metrics
from check_thumb_own_cmc_paths import location

if __name__=='__main__':
    prototypes=[('metacarpal','thumb_cmc_flexion',make_thumb_metacarpal()),
        ('mcp_carrier','thumb_mcp_abduction',bd.Pos(0,36,0)*make_universal_carrier(phalanx_width=16)),
        ('proximal','thumb_mcp_flexion',bd.Pos(0,36,0)*make_phalanx(27,16)),
        ('distal','thumb_ip',bd.Pos(0,63,0)*make_phalanx(21,13,distal=True))]
    for target,y,radius,axis in [('mcp_abduction',36,5.5,'yaw'),('mcp_flexion',36,5.5,'flex'),('ip',63,3.5,'flex')]:
        for sign in(-1,1):
            placement=bd.Pos(0,y,-9.5 if sign>0 else -12) if axis=='yaw' else bd.Pos(sign*.9,y,0)*bd.Rot(0,90,0)
            prototypes.append((f'{target}_{sign}_pulley',f'thumb_{target}',placement*make_pulley(radius)))
        if axis=='flex':prototypes.append((f'{target}_shaft',f'thumb_{target}',bd.Pos(0,y,0)*bd.Cylinder(1,18,rotation=(0,90,0))))
    samples=[('flat',{})]
    for j,values in [('mcp_abduction',[-15,-5,5,15]),('mcp_flexion',range(0,71,10)),('ip',[*range(0,81,10),85])]:
        samples.extend((f'{j}_{q}',{f'thumb_{j}':float(q)}) for q in values)
    samples.extend((f'compound_{q}',{'thumb_mcp_abduction':q,'thumb_mcp_flexion':70.,'thumb_ip':85.}) for q in(-15.,0.,15.))
    if '--neutral-only' in sys.argv:samples=samples[:1]
    report={'scope':[n for n,f,p in prototypes],'rows':[],'pass':False};out=Path(__file__).with_name('thumb_downstream_report.json');cache={}
    short_mcp_yaw='--short-mcp-yaw' in sys.argv
    if short_mcp_yaw:out=Path(__file__).with_name('thumb_downstream_short_candidate_report.json')
    for label,pose in samples:
        print('checking',label,flush=True);routes=thumb_downstream_routes(pose,short_mcp_yaw=short_mcp_yaw);metrics=[route_metrics(r) for r in routes];fk=downstream_transforms(pose)
        solids=[(name,frame,location(fk[frame])*part,part) for name,frame,part in prototypes];bounds={n:p.bounding_box() for n,f,p,o in solids}
        collisions=[];tested=0
        for route in routes:
            for group in route['groups']:
                radius=.45 if group['guide'] in('snug_reaction_liner','fixed_curved_guide') else .3
                wire=path_wire(group['path']);wb=wire.bounding_box()
                for name,frame,part,original in solids:
                    if bbox_gap(wb,bounds[name])>radius+.1:continue
                    local=rounded_data(transform_path(group['path'],np.linalg.inv(fk[frame])));key=(name,json.dumps(local,sort_keys=True));tested+=1
                    if key not in cache:cache[key]=path_wire(local).distance_to(original)-1e-6
                    distance=cache[key]
                    if distance<radius-1e-7:collisions.append({'tendon':route['name'],'group':group['label'],'solid':name,'centerline_distance_mm':distance,'radius':radius})
        conflicts=[];gap=999.
        for i in range(len(routes)):
            tree=cKDTree(metrics[i]['points'])
            for j in range(i+1,len(routes)):
                distance=float(tree.query(metrics[j]['points'],workers=1)[0].min())-(metrics[i]['spacing']+metrics[j]['spacing'])/2-.9;gap=min(gap,distance)
                if distance<0:conflicts.append({'a':routes[i]['name'],'b':routes[j]['name'],'gap_lower_bound_mm':distance})
        row={'label':label,'pose':pose,'minimum_radius_mm':min(m['minimum_bend_radius_mm'] for m in metrics),'maximum_join_gap_mm':max(m['maximum_join_gap_mm'] for m in metrics),'maximum_tangent_error':max(m['maximum_tangent_error'] for m in metrics),'mutual_gap_lower_bound_mm':gap,'mutual_conflicts':conflicts,'collisions':collisions,'exact_distance_tests':tested}
        row['pass']=bool(not collisions and not conflicts and row['minimum_radius_mm']>=3.5-1e-10 and row['maximum_join_gap_mm']<1e-8 and row['maximum_tangent_error']<1e-8)
        report['rows'].append(row);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
    report['pass']=all(r['pass'] for r in report['rows']);out.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
