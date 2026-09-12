"""Deterministic geometric solve for an ideal snug universal-joint Bowden liner.

No CAD kernel is imported. SciPy solves the few control parameters; the result
is canonical cubic path data ready for CAD and the live deformTube renderer.
The declared reaction mechanism is identical to bowden_transport.py.
"""
from functools import lru_cache
from math import cos,sin,radians
import numpy as np
from scipy.optimize import brentq,minimize
from lib.bowden_transport import GAUSS_NODES,GAUSS_WEIGHTS

ANCHOR_DISTANCE=12.25
ANCHOR_Z=0.0
WORKING_LENGTH=28.5
MINIMUM_RADIUS=3.5
SOLVE_RADIUS=3.6
TENDON_RADIUS=.30
LINER_INNER_RADIUS=.30
LINER_OUTER_RADIUS=.45
SIX_LANES=(-5.4,-4.2,-3.0,3.0,4.2,5.4)
FOUR_LANES=(-4.2,-3.0,3.0,4.2)


def _rotate(v,quat):
    w,*xyz=quat;u=np.asarray(xyz);v=np.asarray(v)
    return v+2*np.cross(u,np.cross(u,v)+w*v)


def _datums(flex_deg,yaw_deg,lane_x):
    f,y=radians(flex_deg)/2,radians(yaw_deg)/2
    quat=np.array([cos(y)*cos(f),cos(y)*sin(f),sin(y)*sin(f),sin(y)*cos(f)])
    half=np.array([1+quat[0],*quat[1:]]);half/=np.linalg.norm(half)
    p0=np.array([lane_x,-ANCHOR_DISTANCE,ANCHOR_Z])
    p3=_rotate([lane_x,ANCHOR_DISTANCE,ANCHOR_Z],quat)
    return p0,p3,_rotate([0,0,1],half),_rotate([0,1,0],half),_rotate([0,1,0],quat)


def curves_from_parameters(flex_deg,yaw_deg,lane_x,parameters):
    a,b,d,h=parameters
    p0,p3,normal,tm,t1=_datums(flex_deg,yaw_deg,lane_x)
    middle=(p0+p3)/2+h*normal
    return np.array([[p0,p0+[0,a,0],middle-b*tm,middle],
                     [middle,middle+b*tm,p3-d*t1,p3]])


def _derivatives(curves,t):
    t=np.asarray(t)[None,:,None];c=np.asarray(curves)[:,None,:,:]
    u=3*((1-t)**2*(c[:,:,1]-c[:,:,0])+2*(1-t)*t*(c[:,:,2]-c[:,:,1])+t*t*(c[:,:,3]-c[:,:,2]))
    v=6*((1-t)*(c[:,:,2]-2*c[:,:,1]+c[:,:,0])+t*(c[:,:,3]-2*c[:,:,2]+c[:,:,1]))
    return u,v


def _length(curves):
    u,_=_derivatives(curves,GAUSS_NODES)
    return float(np.sum(np.linalg.norm(u,axis=2)*np.asarray(GAUSS_WEIGHTS)))


def _curvatures(curves):
    u,v=_derivatives(curves,np.linspace(0,1,81))
    return np.linalg.norm(np.cross(u,v),axis=2).ravel()/np.linalg.norm(u,axis=2).ravel()**3


@lru_cache(maxsize=10000)
def solve_parameters(flex_deg,yaw_deg,lane_x):
    if not -25<=flex_deg<=110 or not -20<=yaw_deg<=20:
        raise ValueError('universal Bowden pose outside declared flex/yaw range')
    curves=lambda v:curves_from_parameters(flex_deg,yaw_deg,lane_x,v)
    # Same continuous outward-bulge branch at all poses.
    initial_h=brentq(lambda h:_length(curves([7,7,7,h]))-WORKING_LENGTH,-25,-1)
    initial=np.array([7,7,7,initial_h])
    if _curvatures(curves(initial)).max()<=1/SOLVE_RADIUS:
        return tuple(float(v) for v in initial)
    result=minimize(lambda v:float(np.sum((v[:3]-7)**2)),initial,
        constraints=[{'type':'eq','fun':lambda v:_length(curves(v))-WORKING_LENGTH},
                     {'type':'ineq','fun':lambda v:1/SOLVE_RADIUS-_curvatures(curves(v))}],
        bounds=[(.6,16)]*3+[(-25,-1)],method='SLSQP',
        options={'maxiter':300,'ftol':1e-11})
    if not result.success or abs(_length(curves(result.x))-WORKING_LENGTH)>1e-8 or _curvatures(curves(result.x)).max()>1/3.59:
        raise ValueError(f'Bowden solve failed flex={flex_deg}, yaw={yaw_deg}, lane={lane_x}: {result.message}; length={_length(curves(result.x))}; radius={1/_curvatures(curves(result.x)).max()}')
    return tuple(float(v) for v in result.x)


def bowden_universal(flex_deg=0.0,yaw_deg=0.0,lane_x=3.0):
    parameters=solve_parameters(float(flex_deg),float(yaw_deg),float(lane_x))
    curves=curves_from_parameters(flex_deg,yaw_deg,lane_x,parameters)
    p0,p3,normal,tm,t1=_datums(flex_deg,yaw_deg,lane_x)
    return {'path':[{'kind':'bezier','points':c.tolist()} for c in curves],
            'length':_length(curves),'parameters':list(parameters),
            'inlet':{'point':p0.tolist(),'tangent':[0,1,0],'frame':'parent'},
            'outlet':{'point':p3.tolist(),'tangent':t1.tolist(),'frame':'child'},
            'reaction':'ideal snug inextensible liner',
            'net_moment_arms':{'flexion':0.0,'abduction':0.0}}
