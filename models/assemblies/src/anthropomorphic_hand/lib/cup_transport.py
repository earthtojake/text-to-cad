"""Candidate constant-length palm-cup reaction guides; not yet accepted."""
from functools import lru_cache
from math import radians, sin, cos
import numpy as np
from scipy.optimize import minimize, brentq
from scipy.integrate import quad
from scipy.spatial import cKDTree
from lib.hand_inlets import hand_inlets
from lib.bowden_universal import _length, _curvatures
from lib.bowden_mcp import sampled_points, cylinder_sdf
from lib.palm_path_envelopes import palm_clearances

CUP_ORIGIN=np.array([22.,40.,0.])
ENVELOPE=.48

def cup_datums():
    rows=[]
    for item in hand_inlets():
        if not item['tendon'].startswith('little_'):continue
        end=np.array(item['point']);tangent=np.array(item['tangent'])
        start=end.copy();start[1]=35.
        if '_pip_' in item['tendon'] or '_dip_' in item['tendon']:
            start[0]=end[0]+4.;start[1]=43.
        radial=end[[0,2]]-CUP_ORIGIN[[0,2]]
        length=np.linalg.norm(radial)
        if length<8.5 and '_pip_' not in item['tendon'] and '_dip_' not in item['tendon']:
            radius=9.7 if '_dip_' in item['tendon'] else 8.5
            start[[0,2]]=CUP_ORIGIN[[0,2]]+radial*radius/length
        if '_mcp_flexion_' in item['tendon']:start=np.array([12.,31.,end[2]])
        rows.append({'tendon':item['tendon'],'start':start.tolist(),'end':end.tolist(),'tangent':tangent.tolist(),'length':float(np.linalg.norm(end-start)+4.)})
    return rows


def rotation(q):
    a=radians(-q);c,s=cos(a),sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])


def curves(q,row,v):
    a,b,d,mx,my,mz,theta,psi=v
    rot=rotation(q);p0=np.array(row['start']);p3=CUP_ORIGIN+rot@(np.array(row['end'])-CUP_ORIGIN)
    t0=np.array([0.,1.,0.]);t1=rot@np.array(row['tangent'])
    tm=np.array([sin(psi)*cos(theta),cos(psi)*cos(theta),sin(theta)])
    middle=np.array([mx,my,mz])
    return np.array([[p0,p0+a*t0,middle-b*tm,middle],[middle,middle+b*tm,p3-d*t1,p3]])


def obstacles(points):
    p=np.asarray(points)-CUP_ORIGIN;rad=np.linalg.norm(p[:,[0,2]],axis=1)
    out=[cylinder_sdf(rad-1.,np.maximum(35.-(p[:,1]+40.),(p[:,1]+40.)-75.))-ENVELOPE]
    for plane in (45.,47.):
        out.append(cylinder_sdf(rad-7.5,np.abs(p[:,1]+40.-plane)-.75)-ENVELOPE)
    return np.concatenate(out)


@lru_cache(maxsize=2048)
def solve_cup_packet(q):
    solved=[];cloud=[];previous_distal=None
    rows=sorted(cup_datums(),key=lambda r:(r['end'][2],r['end'][0]))
    for row in rows:
        print('cup solving',q,row['tendon'],flush=True)
        path=lambda v:curves(q,row,v)
        constraints=[{'type':'eq','fun':lambda v:_length(path(v))-row['length']},
                     {'type':'ineq','fun':lambda v:1/3.65-_curvatures(path(v))},
                     {'type':'ineq','fun':lambda v:obstacles(sampled_points(path(v),801))},
                     {'type':'ineq','fun':lambda v:palm_clearances(sampled_points(path(v),201),rotation(q))}]
        if cloud:
            tree=cKDTree(np.array(cloud))
            constraints.append({'type':'ineq','fun':lambda v:tree.query(sampled_points(path(v),401),workers=1)[0]-1.02})
        start=np.array(row['start']);end=CUP_ORIGIN+rotation(q)@(np.array(row['end'])-CUP_ORIGIN)
        handle=(end[1]-start[1])/6
        initials=[]
        from lib.cup_atlas import ATLAS
        if ATLAS['entries']:
            entries=sorted(ATLAS['entries'],key=lambda e:e['angle_deg'])
            lower=max((e for e in entries if e['angle_deg']<=q),key=lambda e:e['angle_deg'],default=entries[0])
            upper=min((e for e in entries if e['angle_deg']>=q),key=lambda e:e['angle_deg'],default=entries[-1])
            va=np.array(next(r for r in lower['packet'] if r['tendon']==row['tendon'])['parameters'])
            vb=np.array(next(r for r in upper['packet'] if r['tendon']==row['tendon'])['parameters'])
            weight=0. if upper['angle_deg']==lower['angle_deg'] else (q-lower['angle_deg'])/(upper['angle_deg']-lower['angle_deg'])
            initials.append(((1-weight)*va+weight*vb).tolist())
        if previous_distal is not None and ('_pip_' in row['tendon'] or '_dip_' in row['tendon']):
            prior,prior_start,prior_end=previous_distal
            seed=prior.copy();seed[3:6]+=(start+end-prior_start-prior_end)/2
            initials.append(seed.tolist())
        for mxoff in (0.,4.,-4.):
            for mzoff in (3.,-3.,0.):
                mid=(start+end)/2+[mxoff,0,mzoff]
                initials.append([handle,handle,handle,*mid,.0,.2])
        best=None
        for seed in initials:
            result=minimize(lambda v:.02*np.sum((v[:3]-handle)**2)+.001*(v[4]-(start[1]+end[1])/2)**2+.005*v[6]**2,seed,
                method='SLSQP',bounds=[(.4,14)]*3+[(0,42),(32,68),(-30,25),(-3,3),(-3,3)],constraints=constraints,
                options={'maxiter':400,'ftol':1e-10})
            cs=path(result.x)
            if abs(_length(cs)-row['length'])<1e-7 and _curvatures(cs).max()<=1/3.64 and obstacles(sampled_points(cs,1001)).min()>-1e-5 and palm_clearances(sampled_points(cs,801),rotation(q)).min()>-1e-5 and (not cloud or tree.query(sampled_points(cs,1001),workers=1)[0].min()>1.0199):
                best=result.x;break
        if best is None:raise ValueError(f"Cup solve failed {q} {row['tendon']}: L={_length(cs)}, R={1/_curvatures(cs).max()}, obstacle={obstacles(sampled_points(cs,1001)).min()}, palm={palm_clearances(sampled_points(cs,801),rotation(q)).min()}, status={result.message}")
        def exact_residual(a):
            v=best.copy();v[0]=a;total=0.
            for c in path(v):total+=quad(lambda t:float(np.linalg.norm(3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2])))),0,1,epsabs=2e-12,epsrel=2e-13)[0]
            return total-row['length']
        best[0]=brentq(exact_residual,best[0]-1e-4,best[0]+1e-4,xtol=1e-13)
        if '_pip_' in row['tendon'] or '_dip_' in row['tendon']:previous_distal=(best.copy(),start.copy(),end.copy())
        cs=path(best);cloud.extend(sampled_points(cs,1201));solved.append({**row,'parameters':best.tolist(),'working_length':row['length'],
            'inlet':{'point':row['start'],'tangent':[0.,1.,0.],'frame':'wrist_flexion'},
            'outlet':{'point':cs[-1,-1].tolist(),'neutral_point':row['end'],
                      'tangent':(rotation(q)@np.array(row['tangent'])).tolist(),'frame':'palm_cup'},
            'neutralizes':['palm_cup'],'reaction':'ideal snug inextensible liner',
            'length_correction':{'variable':'first_handle_length','segment':0,'control':1,
                'anchor_control':0,'direction':'exact_inlet_tangent','initial_value':float(best[0])},
            'path':[{'kind':'bezier','points':c.tolist()} for c in cs]})
    return solved


def cup_fixed_inlets():
    """Parent-side splice contract for the upstream compensated wrist spans."""
    return [{'tendon':row['tendon'],'point':row['start'],'tangent':[0.,1.,0.],
             'frame':'wrist_flexion','moving_outlet':row['end'],
             'working_length':row['length']} for row in cup_datums()]


@lru_cache(maxsize=2048)
def cup_packet(q=0.):
    """Use CAD-audited atlas entries; unlisted angles remain solver candidates."""
    import copy
    from lib.cup_atlas import ATLAS
    if ATLAS['entries']:
        expected={r['tendon']:r for r in cup_datums()}
        for entry in ATLAS['entries']:
            if abs(entry['angle_deg']-q)>1e-10:continue
            for row in entry['packet']:
                datum=expected[row['tendon']]
                if np.linalg.norm(np.array(row['start'])-datum['start'])>1e-9 or np.linalg.norm(np.array(row['end'])-datum['end'])>1e-9 or abs(row['length']-datum['length'])>1e-9:
                    raise ValueError('Cup atlas datum mismatch; geometry must be revalidated')
            return copy.deepcopy(entry['packet'])
    return solve_cup_packet(float(q))
