"""Whole-thumb10-route gate against every current thumb frame and drive body."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from cadgen import build123d as bd
from lib.layout import JOINTS,THUMB_CMC,THUMB_LENGTHS,transforms,drive_pulley_offset
from lib.assembly import joint_location,matrix_location
from lib.thumb_routing import thumb_routes
from lib.phalanx import make_phalanx
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.universal_carrier import make_universal_carrier
from lib.pulley import make_pulley
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
from check_middle_hardware_paths import bbox_gap,rounded_data
from check_middle_routes import route_metrics


def thumb_hardware():
    base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45);out=[];station=0.
    for i,(length,width) in enumerate(zip(THUMB_LENGTHS,(19.,16.,13.))):
        frame=f'thumb_{("cmc_flexion","mcp_flexion","ip")[i]}'
        part=make_thumb_metacarpal() if i==0 else make_phalanx(length,width,distal=i==2)
        out.append((f'frame_{i}',frame,base*bd.Pos(0,station,0)*part))
        out.append((f'shaft_{i}',frame,base*bd.Pos(0,station,0)*bd.Cylinder(1,width,rotation=(0,90,0))))
        if i<2:out.append((f'carrier_{i}',f'thumb_{("cmc","mcp")[i]}_abduction',base*bd.Pos(0,station,0)*make_universal_carrier(phalanx_width=width,yaw_plane=9.5 if i==0 else 8.)))
        station+=length
    for joint in JOINTS:
        if joint.system!='thumb':continue
        for sign in(-1,1):out.append((f'{joint.name}_{sign}_pulley',joint.name,joint_location(joint)*bd.Pos(0,0,drive_pulley_offset(joint,sign))*make_pulley(joint.drive_radius)))
    return out

if __name__=='__main__':
    hardware=thumb_hardware();cache={};report={'scope':[n for n,f,p in hardware],'rows':[],'pass':False};out=Path(__file__).with_name('thumb_full_report.json')
    samples=[('neutral',{}),('cmc_yaw45',{'thumb_cmc_abduction':45.})]
    if '--yaw45-only' in sys.argv:
        samples=samples[1:];out=Path(__file__).with_name('thumb_full_yaw45_report.json')
    for label,pose in samples:
        print('checking',label,flush=True);routes=thumb_routes(pose);metrics=[route_metrics(r) for r in routes];fk=transforms(pose)
        solids=[(name,frame,matrix_location(fk[frame])*part,part) for name,frame,part in hardware];bounds={n:p.bounding_box() for n,f,p,o in solids};collisions=[];tested=0
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
                d=float(tree.query(metrics[j]['points'],workers=1)[0].min())-(metrics[i]['spacing']+metrics[j]['spacing'])/2-.9;gap=min(gap,d)
                if d<0:conflicts.append({'a':routes[i]['name'],'b':routes[j]['name'],'gap_lower_bound_mm':d})
        row={'label':label,'pose':pose,'minimum_radius_mm':min(m['minimum_bend_radius_mm'] for m in metrics),'maximum_join_gap_mm':max(m['maximum_join_gap_mm'] for m in metrics),'maximum_tangent_error':max(m['maximum_tangent_error'] for m in metrics),'minimum_mutual_gap_lower_bound_mm':gap,'mutual_conflicts':conflicts,'collisions':collisions,'exact_distances_tested':tested}
        row['pass']=bool(not collisions and not conflicts and row['minimum_radius_mm']>=3.5-1e-10 and row['maximum_join_gap_mm']<1e-8 and row['maximum_tangent_error']<1e-8)
        report['rows'].append(row);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
    report['pass']=all(r['pass'] for r in report['rows']);out.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
