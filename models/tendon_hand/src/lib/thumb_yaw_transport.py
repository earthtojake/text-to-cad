"""Thumb CMC-flexion reaction liners across the larger CMC yaw range.

The 24.5 mm working centerline length and ±.9mm drive planes are retained.
A free banking angle provides the extra spatial freedom required at yaw45.
Local curve feasibility is independent of the later assembly clearance gate.
"""
from functools import lru_cache
from math import radians,sin,cos,pi
import numpy as np
from scipy.optimize import brentq,minimize
from lib.bowden_universal import _length,_curvatures


def curves(yaw_deg,sign,v):
    angle=radians(yaw_deg);c,s=cos(angle),sin(angle);ch,sh=cos(angle/2),sin(angle/2)
    p0=np.array([sign*.9,-23.,sign*7.]);p3=np.array([sign*.9*c+3*s,sign*.9*s-3*c,sign*7.])
    t1=np.array([-s,c,0.]);tm=np.array([-sh,ch,0.])
    a,b,d,h,bank=v;normal=np.array([-sign*cos(bank)*ch,-sign*cos(bank)*sh,-sign*sin(bank)])
    middle=(p0+p3)/2+h*normal
    return np.array([[p0,p0+[0,a,0],middle-b*tm,middle],[middle,middle+b*tm,p3-d*t1,p3]])


@lru_cache(maxsize=1000)
def parameters(yaw_deg,sign):
    if not -25<=yaw_deg<=45:raise ValueError('CMC yaw outside declared range')
    cs=lambda v:curves(yaw_deg,sign,v)
    for bank in(90.,45.,135.,0.,180.):
        h=brentq(lambda h:_length(cs([5.5,5.5,5.5,h,radians(bank)]))-24.5,-25,-.1)
        initial=np.array([5.5,5.5,5.5,h,radians(bank)])
        if max(_curvatures(cs(initial)))<=1/3.65:return tuple(initial)
        result=minimize(lambda v:float(np.sum((v[:3]-5.5)**2)+.1*(v[4]-pi/2)**2),initial,
            method='SLSQP',bounds=[(.5,16)]*3+[(-25,-.1),(-pi,pi)],
            constraints=[{'type':'eq','fun':lambda v:_length(cs(v))-24.5},
                         {'type':'ineq','fun':lambda v:1/3.65-_curvatures(cs(v))}],
            options={'maxiter':500,'ftol':1e-11})
        if abs(_length(cs(result.x))-24.5)<1e-9 and max(_curvatures(cs(result.x)))<1/3.64:
            return tuple(result.x)
    raise ValueError(f'Thumb CMC yaw liner failed at yaw={yaw_deg}, sign={sign}')


def thumb_yaw_reaction_span(yaw_deg,sign):
    return [{'kind':'bezier','points':c.tolist()} for c in curves(yaw_deg,sign,parameters(float(yaw_deg),int(sign)))]
