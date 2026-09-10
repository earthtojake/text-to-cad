"""PIP reaction liner with explicit clearance around the driven through-shaft."""
from functools import lru_cache
from math import sin,cos,radians
import numpy as np
from scipy.optimize import minimize, brentq
from lib.bowden_universal import _length, _curvatures
from lib.path_analysis import cubic_min_radius, cubic_axis_distance

WORKING_LENGTH = 30.0
SHAFT_RADIUS = 1.0
LINER_OUTER_RADIUS = .45


def pip_curves(angle,lane_x,parameters,child_anchor=12.25):
    q=radians(angle);a,b,d,h=parameters
    p0=np.array([lane_x,-12.25,0.])
    p3=np.array([lane_x,child_anchor*cos(q),child_anchor*sin(q)])
    tm=np.array([0,cos(q/2),sin(q/2)])
    normal=np.array([0,-sin(q/2),cos(q/2)])
    t1=np.array([0,cos(q),sin(q)])
    middle=(p0+p3)/2+h*normal
    return np.array([[p0,p0+[0,a,0],middle-b*tm,middle],
                     [middle,middle+b*tm,p3-d*t1,p3]])


def _points(curves):
    t=np.linspace(0,1,121)[None,:,None]; c=curves[:,None,:,:]
    return (1-t)**3*c[:,:,0]+3*(1-t)**2*t*c[:,:,1]+3*(1-t)*t*t*c[:,:,2]+t**3*c[:,:,3]


@lru_cache(maxsize=1000)
def pip_parameters(angle,child_anchor=12.25):
    curves=lambda v:pip_curves(angle,0,v,child_anchor)
    solve_radius=3.55 if child_anchor<12.25 else 3.60
    h=brentq(lambda h:_length(curves([7,7,7,h]))-WORKING_LENGTH,-30,-1)
    initial=np.array([7,7,7,h])
    def shaft_clearance(v):
        p=_points(curves(v))
        return np.linalg.norm(p[:,:,1:],axis=2).ravel()-1.55
    if shaft_clearance(initial).min()>0 and _curvatures(curves(initial)).max()<1/solve_radius:
        return tuple(initial)
    result=minimize(lambda v:float(np.sum((v[:3]-7)**2)),initial,
        constraints=[{'type':'eq','fun':lambda v:_length(curves(v))-WORKING_LENGTH},
                     {'type':'ineq','fun':lambda v:1/solve_radius-_curvatures(curves(v))},
                     {'type':'ineq','fun':shaft_clearance}],
        bounds=[(.6,16)]*3+[(-25,-1)],method='SLSQP',options={'maxiter':500,'ftol':1e-11})
    c=curves(result.x)
    radius=min(cubic_min_radius(p) for p in c)
    distance=min(cubic_axis_distance(p) for p in c)
    if not result.success or abs(_length(c)-WORKING_LENGTH)>1e-8 or radius<3.5 or distance<1.45:
        raise ValueError(f'PIP shaft solve failed at {angle}: {result.message}; radius={radius}, shaft distance={distance}, length={_length(c)}')
    return tuple(float(x) for x in result.x)


def pip_transport(angle=0.,lane_x=4.2,child_anchor=12.25):
    parameters=pip_parameters(float(angle),float(child_anchor))
    c=pip_curves(angle,lane_x,parameters,child_anchor)
    return {'path':[{'kind':'bezier','points':p.tolist()} for p in c],
            'length':_length(c),'parameters':list(parameters),
            'minimum_radius':min(cubic_min_radius(p) for p in c),
            'shaft_clearance':min(cubic_axis_distance(p) for p in c)-1.45,
            'reaction':'ideal snug inextensible liner', 'net_moment_arm':0.}
