"""Universal MCP reaction liner constrained around actual pulley and shaft volumes.

Inlet anchor Y−12.25; outlet anchor Y+16 in the proximal-phalanx frame.
Fixed working length32 mm. Both yaw drums retain agreed Z±8 datums.
"""
from functools import lru_cache
from math import cos,sin,radians
import numpy as np
from scipy.optimize import minimize
from scipy.spatial import cKDTree
from lib.bowden_universal import _rotate,_length,_curvatures

INLET_DISTANCE=12.25
OUTLET_DISTANCE=20.
WORKING_LENGTH=36.
ENVELOPE=.46  # .45 liner plus .03 sampling reserve
DESIGN_RADIUS=3.60


def datums(flex_deg,yaw_deg,lane):
    f,y=radians(flex_deg)/2,radians(yaw_deg)/2
    quat=np.array([cos(y)*cos(f),cos(y)*sin(f),sin(y)*sin(f),sin(y)*cos(f)])
    p0=np.array([lane,-INLET_DISTANCE,0.]);p3=_rotate([lane,OUTLET_DISTANCE,0.],quat)
    t1=_rotate([0,1,0],quat)
    return p0,p3,t1


def curves(flex_deg,yaw_deg,lane,parameters):
    a,b,d,my,mz,theta,mx_offset,psi_offset=parameters
    p0,p3,t1=datums(flex_deg,yaw_deg,lane)
    ya=radians(yaw_deg)/2+psi_offset
    tm=np.array([-sin(ya)*cos(theta),cos(ya)*cos(theta),sin(theta)])
    middle=np.array([(p0[0]+p3[0])/2+mx_offset,my,mz])
    result=np.array([[p0,p0+[0,a,0],middle-b*tm,middle],
                     [middle,middle+b*tm,p3-d*t1,p3]])
    g0=p0[0];g1=g0;g3=p3[0];g2=g3-2*d*t1[0]
    split=(g0+3*g1+3*g2+g3)/8
    result[0,:,0]=[g0,(g0+g1)/2,(g0+2*g1+g2)/4,split]
    result[1,:,0]=[split,(g1+2*g2+g3)/4,(g2+g3)/2,g3]
    return result


def sampled_points(cs,count=121):
    t=np.linspace(0,1,count)[None,:,None];c=np.asarray(cs)[:,None,:,:]
    return ((1-t)**3*c[:,:,0]+3*(1-t)**2*t*c[:,:,1]+3*(1-t)*t*t*c[:,:,2]+t**3*c[:,:,3]).reshape(-1,3)


def cylinder_sdf(radial,axial):
    return np.sqrt(np.maximum(radial,0)**2+np.maximum(axial,0)**2)+np.minimum(np.maximum(radial,axial),0)


def obstacle_clearances(points,yaw_deg,envelope=ENVELOPE):
    p=np.asarray(points);results=[]
    # Turned yaw drums: maximum radius6 and half width.75.
    for sign in (-1,1):
        results.append(cylinder_sdf(np.linalg.norm(p[:,:2],axis=1)-6.,np.abs(p[:,2]-sign*8)-.75)-envelope)
    q=radians(yaw_deg);c,s=cos(q),sin(q)
    rot=np.array([[c,s,0],[-s,c,0],[0,0,1]])
    local=p@rot.T
    radial=np.linalg.norm(local[:,1:],axis=1)
    # Continuous driven shaft, plus both flexion drive drums.
    results.append(radial-1.-envelope)
    for sign in (-1,1):
        results.append(cylinder_sdf(radial-6.,np.abs(local[:,0]-sign*.9)-.75)-envelope)
    return np.concatenate(results)


@lru_cache(maxsize=10000)
def solve_mcp(flex_deg,yaw_deg,lane):
    if not -15<=flex_deg<=90 or not -25<=yaw_deg<=25:
        raise ValueError('MCP solve outside declared finger ranges')
    target_length=36.5 if abs(lane)<3.5 else WORKING_LENGTH
    cs=lambda v:curves(flex_deg,yaw_deg,lane,v)
    cons=[{'type':'eq','fun':lambda v:_length(cs(v))-target_length},
          {'type':'ineq','fun':lambda v:1/DESIGN_RADIUS-_curvatures(cs(v))},
          {'type':'ineq','fun':lambda v:obstacle_clearances(sampled_points(cs(v)),yaw_deg)}]
    outer_parameters=None
    if abs(lane)<3.5:
        outer_parameters=solve_mcp(flex_deg,yaw_deg,float(np.sign(lane)*4.2))
        outer_cloud=sampled_points(curves(flex_deg,yaw_deg,float(np.sign(lane)*4.2),outer_parameters),801)
        outer_tree=cKDTree(outer_cloud)
        cons.append({'type':'ineq','fun':lambda v:outer_tree.query(sampled_points(cs(v),801),workers=1)[0]-1.02})
    initials=[[5,5,5,4,-4+.065*flex_deg,.5],
              [5,5,5,6,1,1.0],
              [7,5,4,2,-5,.2],
              [4,5,3,7,4,1.3]]
    if flex_deg>60:
        initials.insert(0,[3.,6.,5.25,7.,9.5,1.4])
    initials=[v+[0.,0.] for v in initials]
    if outer_parameters is not None:
        initials.insert(0,list(outer_parameters))
        for advance in (1.0,2.5,4.):
            seed=list(outer_parameters);seed[3]+=advance;seed[6]=0.;seed[7]=0.
            initials.insert(0,seed)
    best=None
    for initial in initials:
        result=minimize(lambda v:float(.02*np.sum((v[:3]-5)**2)+.001*((v[3]-4)**2+(v[4]+1)**2)+.008*v[6]**2+.03*v[7]**2),np.asarray(initial,dtype=float),
                        bounds=[(.5,17)]*3+[(-13,18),(-18,20),(-1.5,3),(0,0),(0,0)],constraints=cons,
                        method='SLSQP',options={'maxiter':500,'ftol':1e-10})
        valid=abs(_length(cs(result.x))-target_length)<1e-8 and _curvatures(cs(result.x)).max()<1/3.59 and obstacle_clearances(sampled_points(cs(result.x)),yaw_deg).min()>-1e-6
        if valid and outer_parameters is not None:
            valid=outer_tree.query(sampled_points(cs(result.x),801),workers=1)[0].min()>=1.01999
        if valid:
            best=result.x;break
    if best is None:
        raise ValueError(f'MCP routing failed flex={flex_deg}, yaw={yaw_deg}, lane={lane}: {result.message}; L={_length(cs(result.x))}, R={1/_curvatures(cs(result.x)).max()}, obstacle={obstacle_clearances(sampled_points(cs(result.x)),yaw_deg).min()}')
    return tuple(float(v) for v in best)


def mcp_crossover(flex_deg=0.,yaw_deg=0.,lane=3.):
    parameters=solve_mcp(float(flex_deg),float(yaw_deg),float(lane));cs=curves(flex_deg,yaw_deg,lane,parameters)
    p0,p3,t1=datums(flex_deg,yaw_deg,lane)
    return {'path':[{'kind':'bezier','points':p.tolist()} for p in cs],
            'parameters':list(parameters),'length':_length(cs),
            'inlet':{'point':p0.tolist(),'tangent':[0,1,0],'frame':'parent'},
            'outlet':{'point':p3.tolist(),'tangent':t1.tolist(),'frame':'child'},
            'net_moment_arms':{'flexion':0.,'abduction':0.}}
