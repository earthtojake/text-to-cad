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

CUP_ORIGIN=np.array([22.,40.,0.])
ENVELOPE=.48

def cup_datums():
    rows=[]
    for item in hand_inlets():
        if not item['tendon'].startswith('little_'):continue
        end=np.array(item['point']);tangent=np.array(item['tangent'])
        start=end-(end[1]-20)/tangent[1]*tangent
        rows.append({'tendon':item['tendon'],'start':start.tolist(),'end':end.tolist(),'tangent':tangent.tolist(),'length':float(np.linalg.norm(end-start)+8.)})
    return rows


def rotation(q):
    a=radians(-q);c,s=cos(a),sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]])


def curves(q,row,v):
    a,b,d,mx,my,mz,theta,psi=v
    rot=rotation(q);p0=np.array(row['start']);p3=CUP_ORIGIN+rot@(np.array(row['end'])-CUP_ORIGIN)
    t0=np.array(row['tangent']);t1=rot@t0
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
def cup_packet(q):
    solved=[];cloud=[]
    rows=sorted(cup_datums(),key=lambda r:(r['end'][2],r['end'][0]))
    for row in rows:
        path=lambda v:curves(q,row,v)
        constraints=[{'type':'eq','fun':lambda v:_length(path(v))-row['length']},
                     {'type':'ineq','fun':lambda v:1/3.65-_curvatures(path(v))},
                     {'type':'ineq','fun':lambda v:obstacles(sampled_points(path(v),241))}]
        if cloud:
            tree=cKDTree(np.array(cloud))
            constraints.append({'type':'ineq','fun':lambda v:tree.query(sampled_points(path(v),401),workers=1)[0]-1.02})
        start=np.array(row['start']);end=CUP_ORIGIN+rotation(q)@(np.array(row['end'])-CUP_ORIGIN)
        initials=[]
        for mxoff in (-8.,-14.,0.,8.):
            for mzoff in (0.,-8.,8.):
                mid=(start+end)/2+[mxoff,0,mzoff]
                initials.append([7.,7.,7.,*mid,.0,.45])
        best=None
        for seed in initials:
            result=minimize(lambda v:.01*np.sum((v[:3]-7.)**2)+.001*(v[4]-39.)**2+.02*v[6]**2,seed,
                method='SLSQP',bounds=[(.5,24)]*3+[(-25,38),(23,53),(-30,25),(-1.4,1.4),(-1.4,1.4)],constraints=constraints,
                options={'maxiter':400,'ftol':1e-10})
            cs=path(result.x)
            if abs(_length(cs)-row['length'])<1e-7 and _curvatures(cs).max()<=1/3.64 and obstacles(sampled_points(cs,1001)).min()>-1e-5 and (not cloud or tree.query(sampled_points(cs,1001),workers=1)[0].min()>1.0199):
                best=result.x;break
        if best is None:raise ValueError(f"Cup solve failed {q} {row['tendon']}: L={_length(cs)}, R={1/_curvatures(cs).max()}, obstacle={obstacles(sampled_points(cs,1001)).min()}, status={result.message}")
        def exact_residual(a):
            v=best.copy();v[0]=a;total=0.
            for c in path(v):total+=quad(lambda t:float(np.linalg.norm(3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2])))),0,1,epsabs=2e-12,epsrel=2e-13)[0]
            return total-row['length']
        best[0]=brentq(exact_residual,best[0]-1e-4,best[0]+1e-4,xtol=1e-13)
        cs=path(best);cloud.extend(sampled_points(cs,1201));solved.append({**row,'parameters':best.tolist(),'path':[{'kind':'bezier','points':c.tolist()} for c in cs]})
    return solved
