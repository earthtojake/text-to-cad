"""Exact OCCT curve-to-solid clearance against finger structure and drive hardware.

A circular tube is contained in its centerline's radius-neighborhood. Thus an
exact wire-to-solid distance greater than its outer radius proves clearance,
including at every point between samples. Own matching liner/tendon surfaces
are certified separately by their shared curve and .30/.30/.45 radial sections.
"""
import json,time
from pathlib import Path
import numpy as np
from cadgen import build123d as bd
from OCP.gp import gp_Trsf
from lib.finger_routing import middle_finger_routes,finger_routes,MIDDLE,yaw_drive_plane,transform_path
from lib.layout import transforms,JOINT_BY_NAME,FINGERS
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley
from lib.universal_carrier import make_universal_carrier
from lib.transport_guide import path_wire


def hardware(include_carrier=True,finger_name="middle"):
    out=[];f=next(f for f in FINGERS if f.name==finger_name);y=f.base_y
    for i,(length,width) in enumerate(zip(f.lengths,f.widths)):
        frame=[f'{finger_name}_mcp_flexion',f'{finger_name}_pip',f'{finger_name}_dip'][i]
        out.append((f'phalanx_{i+1}',frame,bd.Pos(f.x,y,0)*make_phalanx(length,width,distal=i==2)))
        y+=length
    targets=[('mcp_abduction',f.base_y,5.5,'yaw'),('mcp_flexion',f.base_y,5.5,'flex'),('pip',f.base_y+f.lengths[0],4.5,'flex'),('dip',f.base_y+sum(f.lengths[:2]),3.5,'flex')]
    for name,y,radius,axis in targets:
        for sign in(1,-1):
            p=bd.Pos(f.x,y,yaw_drive_plane(sign)) if axis=='yaw' else bd.Pos(f.x+sign*.9,y,0)*bd.Rot(0,90,0)
            out.append((f'{name}_{sign}_pulley',f'{finger_name}_{name}',p*make_pulley(radius)))
        if axis=='flex':
            # Full circular shaft envelope conservatively contains the D shaft.
            out.append((name+'_shaft_envelope',f'{finger_name}_{name}',bd.Pos(f.x,y,0)*bd.Cylinder(1,18,rotation=(0,90,0))))
    if include_carrier:out.append(('mcp_carrier',f'{finger_name}_mcp_abduction',bd.Pos(f.x,f.base_y,0)*make_universal_carrier(phalanx_width=f.widths[0])))
    return out


def bbox_gap(a,b):
    a=a.bounding_box() if hasattr(a,"bounding_box") else a
    b=b.bounding_box() if hasattr(b,"bounding_box") else b
    return sum(max(0,getattr(a.min,k)-getattr(b.max,k),getattr(b.min,k)-getattr(a.max,k))**2 for k in('X','Y','Z'))**.5


DISTANCE_CACHE={}

def rounded_data(value):
    if isinstance(value,dict):return {k:rounded_data(v) for k,v in value.items()}
    if isinstance(value,list):return [rounded_data(v) for v in value]
    if isinstance(value,(float,int)):return round(float(value),8)
    return value


def check(pose,prototypes,finger_name="middle"):
    fk=transforms(pose)
    solids=[]
    prototype_map={name:part for name,frame,part in prototypes}
    frame_map={name:frame for name,frame,part in prototypes}
    for name,frame,part in prototypes:
        transform=gp_Trsf();transform.SetValues(*fk[frame][:3,:].ravel().tolist())
        solids.append((name,bd.Location(transform)*part))
    bounds={name:part.bounding_box() for name,part in solids}
    rows=[];tested=0
    for route in finger_routes(finger_name,pose):
        for group in route['groups']:
            radius=.45 if group['guide'] in('snug_reaction_liner','fixed_curved_guide') else .30
            wire=path_wire(group['path']);wire_bounds=wire.bounding_box()
            for name,part in solids:
                bound=bbox_gap(wire_bounds,bounds[name])
                if bound>radius+.1:continue
                local_path=transform_path(group['path'],np.linalg.inv(fk[frame_map[name]]))
                local_path=rounded_data(local_path)
                key=(finger_name,name,json.dumps(local_path,sort_keys=True,default=float))
                matching_pulley=name==route['joint'].removeprefix(finger_name+'_')+'_'+str(route['sign'])+'_pulley'
                rotational_orbit=(matching_pulley and len(local_path)==1 and local_path[0]['kind']=='arc')
                if rotational_orbit:
                    key=(finger_name,name,'complete_revolved_drive_orbit')
                # Rigid groups in the same attachment frame are reused exactly.
                if key in DISTANCE_CACHE:distance=DISTANCE_CACHE[key]
                else:
                    started=time.monotonic()
                    if rotational_orbit:
                        # The pulley is an exact surface of revolution about
                        # this drive circle's axis, so distance is constant
                        # on its entire circular orbit, not only at endpoints.
                        distance=bd.Vertex(*local_path[0]['start']).distance_to(prototype_map[name])-1e-6
                    else:distance=path_wire(local_path).distance_to(prototype_map[name])-1e-6
                    DISTANCE_CACHE[key]=distance
                    elapsed=time.monotonic()-started
                    if elapsed>2:print('distance_seconds',round(elapsed,2),group['label'],name,flush=True)
                tested+=1
                if distance<radius-1e-7:
                    rows.append({'tendon':route['name'],'group':group['label'],'solid':name,'centerline_distance_mm':distance,'outer_radius_mm':radius,'clearance_mm':distance-radius})
    return {'pose':pose,'exact_distances_tested':tested,'collisions':rows}


if __name__=='__main__':
    import sys
    prototypes=hardware();samples=[('flat_open',{})]
    scope='all_hardware'
    if '--without-carrier' in sys.argv:
        prototypes=[p for p in prototypes if p[0]!='mcp_carrier'];scope='phalanges_pulleys_shafts'
    if '--only-carrier' in sys.argv:
        prototypes=[p for p in prototypes if p[0]=='mcp_carrier'];scope='carrier'
    report_path=Path(__file__).with_name('middle_'+scope+'_paths_report.json')
    if '--all' in sys.argv:
        joints=['middle_mcp_abduction','middle_mcp_flexion','middle_pip','middle_dip']
        for j in joints:
            lo,hi=JOINT_BY_NAME[j].limits
            for q in sorted(set(list(np.arange(lo,hi+1e-8,10))+[hi])):samples.append((f'{j}_{q:g}',{j:float(q)}))
        samples.extend([('full_fist',dict(zip(joints,[0,90,110,80]))),('precision_pinch',dict(zip(joints,[0,40,60,30]))),('spread_flex',dict(zip(joints,[15,90,110,80])))])
    results=[]
    for label,pose in samples:
        print('checking',label,flush=True)
        results.append({'label':label,**check(pose,prototypes)})
        report_path.write_text(json.dumps({'scope':scope,'rows':results},indent=2)+'\n')
        print(json.dumps(results[-1]),flush=True)
    if any(r['collisions'] for r in results):raise SystemExit(1)
