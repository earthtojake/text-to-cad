"""Exact full-route clearance against current complete integration hardware.

Uses stable imported palm bodies to avoid rebuilding their expensive blends.
All other shapes come from the authoritative integration registry, including
real shafts, bushings, rings, wrist frames and the48 actuator assemblies.
Run after freezing the wrist packet and cup/thumb atlas used for that pose.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from cadgen import build123d as bd
from lib import assembly
from lib.layout import assembled_transforms,TENDONS
from lib.hand_routing import full_tendon_routes
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
from lib.path_analysis import sample_path
from check_middle_hardware_paths import bbox_gap,rounded_data
from check_hand_route_pairs import group_radius
from path_solid_clearance import boundary_separation


_BOUND_PROTOTYPES={}
def placed_bounds(bodies):
    """Conservative world boxes from each exact shared prototype box once."""
    from OCP.TopLoc import TopLoc_Location
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from types import SimpleNamespace
    import itertools
    prototypes=_BOUND_PROTOTYPES;result={}
    for i,body in enumerate(bodies):
        wrapped=body.shape.wrapped;local=wrapped.Located(TopLoc_Location());key=hash(local)
        bucket=prototypes.setdefault(key,[])
        cached=next((entry for entry in bucket if entry[0].IsSame(local)),None)
        if cached is None:
            box=Bnd_Box();BRepBndLib.AddOptimal_s(local,box,False,False)
            cached=(local,box.Get());bucket.append(cached)
        limits=cached[1];transform=wrapped.Location().Transformation()
        matrix=np.array([[transform.Value(r,c) for c in range(1,5)] for r in range(1,4)])
        corners=np.array([[*xyz,1.] for xyz in itertools.product(*[(limits[j],limits[j+3]) for j in range(3)])])
        points=corners@matrix.T
        result[body.name]=SimpleNamespace(min=bd.Vector(*points.min(axis=0)),max=bd.Vector(*points.max(axis=0)))
        if i%200==0:print('bounded',i+1,'bodies;',sum(map(len,prototypes.values())),'exact prototypes',flush=True)
    return result


def integration_hardware():
    palm_file=Path('models/assemblies/STEP/anthropomorphic_hand/imported/palm_frame_integration.step')
    little_file=Path('models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step')
    little=list(bd.import_step(str(little_file)).children)[0];little.label='fifth_metacarpal_cupping_truss'
    original=assembly.make_little_metacarpal
    assembly.make_little_metacarpal=lambda:little
    try:bodies=assembly.integration_bodies()
    finally:assembly.make_little_metacarpal=original
    evidence={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in(palm_file,little_file)}
    return bodies,evidence


def audit(routes,bodies,pose,cache=None):
    cache={} if cache is None else cache;fk=assembled_transforms(pose)
    print('placing hardware',flush=True)
    solids=assembly.posed_bodies(bodies,pose)
    print('bounding hardware',flush=True)
    bounds=placed_bounds(solids)
    body_lows=np.array([tuple(bounds[b.name].min) for b in solids])
    body_highs=np.array([tuple(bounds[b.name].max) for b in solids])
    print('starting route/body pairs',flush=True)
    originals={b.name:b for b in bodies};collisions=[];checks=0;route_rows=[];solid_proofs=[];tube_cache={}
    manifest={t['name']:t for t in TENDONS}
    for index,route in enumerate(routes):
        route_checks=0;route_collisions=[]
        for group in route['groups']:
            radius=group_radius(group)
            # Every point of the exact curve is within0.25mm of this cloud:
            # sample_path bounds arc length by the cubic derivative hull.
            # Distance to a containing solid AABB is a lower bound. This only
            # rejects pairs proven separated; all remaining pairs use OCCT.
            cloud=sample_path(group['path'],.5)
            low=cloud.min(axis=0)-.250001;high=cloud.max(axis=0)+.250001
            separations=np.linalg.norm(np.maximum(np.maximum(low-body_highs,body_lows-high),0.),axis=1)
            for body_index in np.flatnonzero(separations<=radius+.1):
                body=solids[body_index]
                box=bounds[body.name];lo=np.array(tuple(box.min));hi=np.array(tuple(box.max))
                delta=np.maximum(np.maximum(lo-cloud,cloud-hi),0.)
                if float(np.linalg.norm(delta,axis=1).min())-.250001>radius:continue
                if group.get('guide')=='capstan' and body.kind in ('capstan','terminal_ferrule','capstan_terminal_bond_line') and body.name.startswith(manifest[route['name']]['actuator']+'_'):
                    # The wire radius envelope extends beyond a flat rope end,
                    # which intentionally abuts its terminal cap. Test the real
                    # swept solid here. All repeated stations use congruent
                    # geometry; canonical path equality makes reuse explicit.
                    tendon=manifest[route['name']];sign=tendon['sign']
                    placement=np.eye(4);placement[:3,:3]=np.diag([sign,1.,sign]);placement[:3,3]=tendon['capstan_center']
                    inverse=np.linalg.inv(placement);local=transform_path(group['path'],inverse)
                    path_key=json.dumps(rounded_data(local),sort_keys=True);key=('actual_stored_rope',body.kind,path_key)
                    if key not in cache:
                        from lib.transport_guide import make_tendon
                        if path_key not in tube_cache:
                            print('constructing exact unrounded stored-rope sweep',flush=True)
                            tube_cache[path_key]=make_tendon(local,'audited_stored_rope')
                        canonical=assembly.matrix_location(inverse)*originals[body.name].shape
                        print('exact stored-rope solid intersection',body.kind,flush=True)
                        common=tube_cache[path_key]&canonical
                        cache[key]=float(common.volume if common else 0.)
                    volume=cache[key];checks+=1;route_checks+=1
                    solid_proofs.append({'tendon':route['name'],'body':body.name,'intersection_mm3':volume,
                                         'method':'exact swept-solid Boolean; congruent actuator copies share canonical path/geometry proof'})
                    if volume>1e-8:
                        failure={'tendon':route['name'],'group':group['label'],'body':body.name,'intersection_mm3':volume}
                        collisions.append(failure);route_collisions.append(failure)
                    continue
                if group.get('guide')=='drive_pulley' and body.name.startswith(route['name']+'_drive_'):
                    # Blind driven ferrules intentionally touch the flat rope
                    # endpoint. Test the actual swept terminal arc, including
                    # its end cap, rather than a spherical endpoint envelope.
                    from lib.transport_guide import make_tendon
                    local=transform_path(group['path'],np.linalg.inv(fk[body.frame]))
                    path_key=json.dumps(rounded_data(local),sort_keys=True)
                    key=('actual_driven_rope',body.name,path_key)
                    if key not in cache:
                        if path_key not in tube_cache:tube_cache[path_key]=make_tendon(local,'audited_driven_rope')
                        common=tube_cache[path_key]&originals[body.name].shape
                        cache[key]=float(common.volume if common else 0.)
                    volume=cache[key];checks+=1;route_checks+=1
                    solid_proofs.append({'tendon':route['name'],'body':body.name,'intersection_mm3':volume,'method':'exact swept terminal arc Boolean, preserving flat endpoint'})
                    if volume>1e-8:
                        failure={'tendon':route['name'],'group':group['label'],'body':body.name,'intersection_mm3':volume}
                        collisions.append(failure);route_collisions.append(failure);print('ROUTE COLLISION',failure,flush=True)
                    continue
                local=transform_path(group['path'],np.linalg.inv(fk[body.frame]))
                key=(body.name,json.dumps(rounded_data(local),sort_keys=True))
                if key not in cache:cache[key]=path_wire(local).distance_to(originals[body.name].shape)-1e-6
                distance=cache[key];checks+=1;route_checks+=1
                if distance <= 0 and distance < radius-1e-7:
                    proof_key=('boundary_separation',*key,radius)
                    if proof_key not in cache:
                        cache[proof_key]=boundary_separation(path_wire(local),originals[body.name].shape,radius)
                    proof=cache[proof_key]
                    if proof['proven_separated']:
                        distance=proof['boundary_distance_mm']-1e-6
                        solid_proofs.append({'tendon':route['name'],'group':group['label'],
                                             'body':body.name,**proof})
                if distance<radius-1e-7:
                    failure={'tendon':route['name'],'group':group['label'],'body':body.name,'body_kind':body.kind,'centerline_distance_lower_bound_mm':distance,'path_outer_radius_mm':radius,'surface_gap_lower_bound_mm':distance-radius}
                    collisions.append(failure);route_collisions.append(failure)
                    print('ROUTE COLLISION',failure,flush=True)
        route_rows.append({'tendon':route['name'],'exact_distances_tested':route_checks,'clear':not route_collisions,'collisions':route_collisions})
        print(f"checked {index+1}/48 {route['name']}: {route_checks} exact distances, {len(route_collisions)} collisions",flush=True)
    return {'pose':pose,'body_count':len(bodies),'exact_distances_tested':checks,'tendon_table':route_rows,'collisions':collisions,'stored_rope_solid_proofs':solid_proofs,'pass':not collisions}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pose',default='{}');parser.add_argument('--wrist-file',default='models/assemblies/validation/anthropomorphic_hand/wrist_transport_neutral.json');parser.add_argument('--out',default='models/assemblies/validation/anthropomorphic_hand/full_route_bodies_neutral.json');args=parser.parse_args()
    pose=json.loads(args.pose);wrist_path=Path(args.wrist_file);wrist_data=json.loads(wrist_path.read_text());wrist=wrist_data['routes'] if isinstance(wrist_data,dict) else wrist_data
    print('constructing current integration hardware',flush=True);bodies,evidence=integration_hardware();print('hardware bodies',len(bodies),flush=True)
    if not pose:
        from lib.neutral_routes import NEUTRAL_ROUTES
        routes=NEUTRAL_ROUTES
        print('using frozen neutral paths from rendered assembly',flush=True)
    else:
        routes=full_tendon_routes(wrist,pose)
    report=audit(routes,bodies,pose);report['input_sha256']={**evidence,str(wrist_path):hashlib.sha256(wrist_path.read_bytes()).hexdigest()}
    report['scope']='all48 full tendon paths versus every body in the current integration registry; future added hardware must be rechecked'
    Path(args.out).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':report['pass'],'body_count':report['body_count'],'exact_distances_tested':report['exact_distances_tested'],'collision_count':len(report['collisions'])}),flush=True)
    if not report['pass']:raise SystemExit(1)
