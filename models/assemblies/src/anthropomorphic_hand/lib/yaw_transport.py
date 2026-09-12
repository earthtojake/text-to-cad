"""Fixed-length reaction liners crossing MCP yaw for its flexion pair."""
from math import radians,cos,sin
import numpy as np
from scipy.optimize import brentq,minimize
from lib.bowden_universal import _length,_curvatures

def yaw_reaction_span(yaw_deg,sign):
    """24.5 mm yaw-neutral liner; stops3 mm before its target drive groove."""
    angle=radians(yaw_deg);c,s=cos(angle),sin(angle);ch,sh=cos(angle/2),sin(angle/2)
    p0=np.array([sign*.9,-23.,sign*5.5]);p3=np.array([sign*.9*c+3*s,sign*.9*s-3*c,sign*5.5])
    t1=np.array([-s,c,0]);tm=np.array([-sh,ch,0])
    bank=radians(90)
    normal=np.array([-sign*cos(bank)*ch,-sign*cos(bank)*sh,-sign*sin(bank)])
    def curves(v):
        a,b,d,h=v;mid=(p0+p3)/2+h*normal
        return np.array([[p0,p0+[0,a,0],mid-b*tm,mid],
                         [mid,mid+b*tm,p3-d*t1,p3]])
    h=brentq(lambda h:_length(curves([5.5,5.5,5.5,h]))-24.5,-20,-.1)
    parameters=np.array([5.5,5.5,5.5,h])
    if _curvatures(curves(parameters)).max()>1/3.65:
        result=minimize(lambda v:float(np.sum((v[:3]-5.5)**2)),parameters,
            constraints=[{'type':'eq','fun':lambda v:_length(curves(v))-24.5},
                         {'type':'ineq','fun':lambda v:1/3.65-_curvatures(curves(v))}],
            bounds=[(.5,16)]*3+[(-20,-.1)],method='SLSQP',options={'maxiter':300,'ftol':1e-11})
        parameters=result.x
        if not result.success or abs(_length(curves(parameters))-24.5)>1e-8:
            raise ValueError(f'MCP flexion yaw-reaction solve failed at{yaw_deg}: {result.message}')
    return [{'kind':'bezier','points':p.tolist()} for p in curves(parameters)]

