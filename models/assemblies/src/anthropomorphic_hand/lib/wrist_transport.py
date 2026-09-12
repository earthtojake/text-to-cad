"""Visible compliant guide spans through the wrist and into the palm.

The spans end at hand-side fixed routing datums. Their measured length change
is explicitly included in each capstan's payout equation. This module does
not infer clearance from a smooth picture: pair and solid gates are separate.
The guide shoes in this region are compliant polymer, not deforming aluminum.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.spatial import cKDTree
from lib.layout import TENDONS,transforms
from lib.hand_inlets import hand_inlets


def inlet_manifest():
    from lib.cup_transport import cup_fixed_inlets
    rows=[r for r in hand_inlets() if not r['tendon'].startswith('little_')]
    rows += cup_fixed_inlets()
    rows += [{'tendon':'palm_cup_'+suffix,'point':[2.,y,z],
              'tangent':[1.,0.,0.],'frame':'wrist_flexion'}
             for suffix,y,z in [('positive',45.,7.),('negative',47.,-7.)]]
    for sign,suffix in ((1,'positive'),(-1,'negative')):
        rows.append({'tendon':'wrist_abduction_'+suffix,'point':[-sign*11.,-15.,sign*5.5],
                     'tangent':[0.,1.,0.],'frame':'forearm'})
        rows.append({'tendon':'wrist_flexion_'+suffix,'point':[sign*14.,-6.,sign*11.],
                     'tangent':[0.,1.,0.],'frame':'wrist_abduction'})
    return {r['tendon']:r for r in rows}


def endpoints(tendon,pose=None):
    _,y,_=tendon['capstan_center'];row=round((y+252.)/41.)
    a=np.array([tendon['bundle_lane'],-12.,tendon['sign']*(43.-1.2*row)])
    inlet=inlet_manifest()[tendon['name']]
    m=transforms(pose or {})[inlet['frame']]
    b=(m@np.array([*inlet['point'],1.]))[:3]
    tangent=m[:3,:3]@np.array(inlet['tangent'])
    return a,b,tangent


def curves(a,b,tangent,parameters):
    lead,tail,handle,dx,dy,dz=parameters[:6]
    turn=np.asarray(parameters[6:9]) if len(parameters)>6 else np.zeros(3)
    direction=(b-a)/np.linalg.norm(b-a)
    middle=(a+b)/2+np.array([dx,dy,dz])
    handle_vector=handle*direction+turn
    return [np.array([a,a+[0,lead,0],middle-handle_vector,middle]),
            np.array([middle,middle+handle_vector,b-tail*tangent,b])]


def values(controls,ts):
    t=np.asarray(ts)[:,None];u=1-t;p=np.asarray(controls)
    points=u**3*p[0]+3*u*u*t*p[1]+3*u*t*t*p[2]+t**3*p[3]
    d=3*(u*u*(p[1]-p[0])+2*u*t*(p[2]-p[1])+t*t*(p[3]-p[2]))
    dd=6*(u*(p[2]-2*p[1]+p[0])+t*(p[3]-2*p[2]+p[1]))
    curvature=np.linalg.norm(np.cross(d,dd),axis=1)/np.maximum(np.linalg.norm(d,axis=1),1e-9)**3
    return points,curvature



def rib_trees():
    """Rounded wrist struts; samples carry a conservative covering reserve."""
    from functools import lru_cache
    return _rib_trees()


from functools import lru_cache
@lru_cache(maxsize=1)
def _rib_trees():
    from lib.path_analysis import sample_path
    groups={}
    def rib(frame,controls,radius):
        key=(frame,radius*.6+.05)
        groups.setdefault(key,[]).extend(sample_path([{'kind':'bezier','points':controls}],.04))
    for sign in (-1,1):
        x=sign*20.
        rib('wrist_flexion',[(x,3.6,0),(sign*23,9,0),(sign*24,9,-7),(sign*24,14,-13.4)],1.35)
        rib('wrist_flexion',[(x,0,-3.6),(sign*23,2,-9),(sign*24,8,-14),(sign*24,14,-13.4)],1.35)
        rib('wrist_abduction',[(sign*1.3,-12.3,0),(sign*8,-21,0),(sign*17,-21,0),(sign*17,-5.3,0)],1.4)
    rib('wrist_flexion',[(-24,14,-13.4),(-12,19,-16.5),(12,19,-16.5),(24,14,-13.4)],1.4)
    for z in (-9.,9.):
        for x in (-10.,10.):
            rib('forearm',[(x*.41,-13.1,z),(x*.8,-17,z),(x,-23,z+(2.2 if z>0 else -2.2)),(x,-30,z+(2.2 if z>0 else -2.2))],1.5)
    for x in (-10.,10.):rib('forearm',[(x,-30,-6.5),(x,-34,-4),(x,-34,4),(x,-30,6.5)],1.5)
    rib('forearm',[(-7.5,-30,-9),(-4,-32,-9),(4,-32,-9),(7.5,-30,-9)],1.3)
    return [(frame,radius,cKDTree(np.asarray(points))) for (frame,radius),points in groups.items()]


def hardware_clearances(points,pose=None):
    """Conservative solid cylinder envelopes for wrist drums and bearing eyes."""
    fk=transforms(pose or {})
    result=[]
    specs=[('wrist_abduction',(0,-9,0),(0,0,1),3.,12.5),
           ('wrist_flexion',(0,0,0),(1,0,0),3.,23.)]
    for sign in (-1,1):
        specs.extend([('wrist_abduction',(0,-9,sign*5.5),(0,0,1),11.5,.75),
                      ('wrist_flexion',(sign*14,0,0),(1,0,0),11.5,.75),
                      ('forearm',(0,-9,sign*9),(0,0,1),6.5,1.5),
                      ('wrist_abduction',(sign*17,0,0),(1,0,0),6.5,1.5),
                      ('wrist_flexion',(sign*20,0,0),(1,0,0),4.6,1.2),
                      ('wrist_flexion',(sign*24,14,-13.4),(0,0,1),3.3,1.2),
                      # Includes the continuous0.20mm structural wall around
                      # the1.65mm mounting bore, not merely the bolt envelope.
                      ('wrist_flexion',(sign*24,14,-10.2),(0,0,1),1.85,1.6),
                      ('wrist_flexion',(sign*24,14,-7.9),(0,0,1),2.75,.7)])
    for frame,center,axis,radius,half_length in specs:
        m=fk[frame];center=(m@np.r_[center,1.])[:3];axis=m[:3,:3]@np.array(axis)
        delta=points-center;axial=delta@axis
        radial=np.linalg.norm(delta-axial[:,None]*axis,axis=1)-radius
        ends=np.abs(axial)-half_length
        distance=np.minimum(np.maximum(radial,ends),0)+np.hypot(np.maximum(radial,0),np.maximum(ends,0))
        result.append(distance)
    for frame,radius,tree in rib_trees():
        m=fk[frame];local=(points-m[:3,3])@m[:3,:3]
        result.append(tree.query(local)[0]-radius)
    return np.concatenate(result)


@lru_cache(maxsize=96)
def hand_obstacle_clouds(pose_items):
    from lib.hand_routing import hand_side_routes
    from lib.path_analysis import sample_path
    result=[]
    for route in hand_side_routes(dict(pose_items)):
        for group in route['groups']:
            radius=.45 if group.get('guide') in ('snug_reaction_liner','fixed_curved_guide') else .30
            result.append((route['name'],radius,sample_path(group['path'],.025)))
    return result


def hand_obstacle_trees(name,pose):
    groups={}
    for other,radius,cloud in hand_obstacle_clouds(tuple(sorted((pose or {}).items()))):
        if other!=name:groups.setdefault(radius,[]).append(cloud)
    return [(radius,cKDTree(np.concatenate(clouds))) for radius,clouds in groups.items()]


def plan_span(tendon,pose=None,previous_cloud=None,seed=None):
    a,b,tangent=endpoints(tendon,pose)
    chord=np.linalg.norm(b-a)
    initial=np.array([chord/6,chord/6,chord/7,0.,0.,0.,0.,0.,0.]) if seed is None else np.array(seed)
    if len(initial)==6:initial=np.r_[initial,np.zeros(3)]
    tree=cKDTree(previous_cloud) if previous_cloud is not None and len(previous_cloud) else None
    hand_trees=hand_obstacle_trees(tendon['name'],pose)
    ts=np.linspace(0,1,101)
    def constraints(p):
        pieces=curves(a,b,tangent,p);vs=[values(c,ts) for c in pieces]
        points=np.concatenate([v[0] for v in vs])
        out=[1/3.8-np.concatenate([v[1] for v in vs]),hardware_clearances(points,pose)-.55]
        if tendon['name']=='index_mcp_abduction_positive':
            # This foreign span must clear the complete CMC carrier/bearing
            # envelope; the thumb's own anchored routes are handled separately.
            from lib.layout import THUMB_CMC
            center=(transforms(pose or {})['wrist_flexion']@np.r_[THUMB_CMC,1.])[:3]
            out.append(np.linalg.norm(points-center,axis=1)-22.55)

        out += [tree.query(points)[0]-(.45+radius+.05) for radius,tree in hand_trees]
        if tree is not None:
            # Previous paths are sampled at <=0.1 mm spacing. A generous
            # candidate margin covers the current constraint grid; the finer
            # complete-curve spacing audit remains mandatory.
            # The six tilted thumb inlet lanes have a certified transverse
            # spacing of 0.983 mm. Retain the larger candidate reserve away
            # from that anchored packet; final complete-path checks use
            # 0.025 mm samples and the same physical 0.45 mm guide radius.
            reserve=np.where((np.linalg.norm(points-b,axis=1)<5.),.96,1.12)
            out.append(tree.query(points)[0]-reserve)
        return np.concatenate(out)
    def objective(p):
        return float(np.sum(((p-initial)/[20,20,20,12,12,12,12,12,12])**2))
    bounds=[(2.,60.),(2.,60.),(2.,60.),(-30.,30.),(-25.,25.),(-35.,35.),
            (-30.,30.),(-30.,30.),(-30.,30.)]
    guesses=[initial]
    if tree is not None:
        for dx,dy,dz in [(0,0,8),(0,0,-8),(8,0,0),(-8,0,0),
                         (0,-12,15),(0,-12,-15),(15,0,15),(-15,0,-15),
                         (0,15,15),(0,15,-15),(25,20,0),(-25,20,0),(0,25,0)]:
            p=initial.copy();p[3:6]+=[dx,dy,dz];guesses.append(p)
    for guess in guesses:
        result=minimize(objective,guess,method='SLSQP',bounds=bounds,
                        constraints={'type':'ineq','fun':constraints},
                        options={'maxiter':500,'ftol':1e-9})
        minimum=float(constraints(result.x).min())
        if minimum>=-1e-6:
            # Refine the candidate constraint grid before the independent
            # complete-curve clearance audit. Short local crossings can
            # sit between a coarse optimizer's samples.
            ts=np.linspace(0,1,501)
            if constraints(result.x).min() < -1e-6:
                result=minimize(objective,result.x,method='SLSQP',bounds=bounds,
                    constraints={'type':'ineq','fun':constraints},
                    options={'maxiter':400,'ftol':1e-9})
            minimum=float(constraints(result.x).min())
            if minimum>=-1e-6:break
    if minimum < -1e-6:
        raise ValueError(f'{tendon["name"]}: wrist guide solve failed ({result.message}); constraint {minimum}')
    return {'name':tendon['name'],'path':[{'kind':'bezier','points':p.tolist()} for p in curves(a,b,tangent,result.x)],
            'parameters':result.x.tolist(),'solver_success':bool(result.success),
            'constraint_margin':minimum,'compensation':'full measured wrist-span length change'}
