"""Canonical six-turn storage helix, authored as C1 cubic Bezier quarters.

Dimensions mm, angles radians. These same curves cut the CAD groove and deform
its tendon. The cubic radial deviation from R7 is below 0.002 mm. A moving exit
is a de Casteljau subdivision of the physical groove, never a new fitted curve.
"""
import math
import numpy as np

PITCH_RADIUS=7.0
PITCH=.8
TURNS=6
START_Z=-2.4
ROPE_RADIUS=.30
GROOVE_RADIUS=.35
OPERATIONAL_ROTATION_LIMIT_RAD=5*math.pi  # half-turn flange reserve at each end
_K=4*(math.sqrt(2)-1)/3


def _quarter(i):
    a=i*math.pi/2; z=START_Z+i*PITCH/4; dz=PITCH/4
    c,s=math.cos(a),math.sin(a)
    xy=((7,0),(7,7*_K),(7*_K,7),(0,7))
    return np.array([[c*x-s*y,s*x+c*y,z+j*dz/3] for j,(x,y) in enumerate(xy)])


def point(points,t):
    p=np.asarray(points,float); u=1-t
    return u**3*p[0]+3*u*u*t*p[1]+3*u*t*t*p[2]+t**3*p[3]


def derivative(points,t):
    p=np.asarray(points,float);u=1-t
    return 3*(u*u*(p[1]-p[0])+2*u*t*(p[2]-p[1])+t*t*(p[3]-p[2]))


def _split_left(p,t):
    a=(1-t)*p[:-1]+t*p[1:];b=(1-t)*a[:-1]+t*a[1:];c=(1-t)*b[0]+t*b[1]
    return np.array([p[0],a[0],b[0],c])


def _parameter_at_angle(phi):
    p=_quarter(0); lo,hi=0.,1.
    for _ in range(48):
        t=(lo+hi)/2;v=point(p,t)
        if math.atan2(v[1],v[0])<phi:lo=t
        else:hi=t
    return (lo+hi)/2


def stored_path(rotation_rad=0., turns=3.):
    """Rotated stored rope from captured end to a fixed azimuth +X exit.

    At q=0 the nominal stored amount is three turns. Positive q pays out rope:
    the groove extent is 2*pi*turns-q. Valid extent is 0..six turns. Rotation
    changes the exit's axial coordinate, which the external lead must follow.
    The tendon termination and spool must both rotate by q about local +Z.
    """
    end=2*math.pi*turns-rotation_rad
    if not 0<end<=2*math.pi*TURNS+1e-10:raise ValueError('storage exhausted: require 0 < stored turns <= 6')
    n=int(math.floor(end/(math.pi/2)+1e-12)); frac=end-n*math.pi/2
    segments=[_quarter(i) for i in range(n)]
    if frac>1e-10:segments.append(_split_left(_quarter(n),_parameter_at_angle(frac)))
    c,s=math.cos(rotation_rad),math.sin(rotation_rad); rot=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
    return [{'kind':'bezier','points':(p@rot.T).tolist()} for p in segments]


def full_groove_path():return stored_path(0.,TURNS)


def endpoint(path):return np.asarray(path[-1]['points'][-1])


def tangent(path,at_start=False):
    p=np.asarray(path[0 if at_start else -1]['points']);v=p[1]-p[0] if at_start else p[-1]-p[-2]
    return v/np.linalg.norm(v)


def path_length(path):
    xs,ws=np.polynomial.legendre.leggauss(20)
    return sum(sum(w*np.linalg.norm(derivative(seg['points'],(x+1)/2))/2 for x,w in zip(xs,ws)) for seg in path)


def prefix_length(path,length):
    """Exact subcurve prefix with a prescribed arc length (for terminal ferrule)."""
    if length<=0:raise ValueError('length must be positive')
    out=[]
    for seg in path:
        L=path_length([seg])
        if length>=L:out.append(seg);length-=L;continue
        p=np.asarray(seg['points']);lo,hi=0.,1.
        for _ in range(45):
            t=(lo+hi)/2;part={'kind':'bezier','points':_split_left(p,t).tolist()}
            if path_length([part])<length:lo=t
            else:hi=t
        out.append({'kind':'bezier','points':_split_left(p,(lo+hi)/2).tolist()});return out
    if length>1e-8:raise ValueError('prefix longer than path')
    return out


def sampled_min_radius(path,samples=101):
    result=float('inf')
    for seg in path:
        p=np.asarray(seg['points'])
        for t in np.linspace(0,1,samples):
            d=derivative(p,t);dd=6*((1-t)*(p[2]-2*p[1]+p[0])+t*(p[3]-2*p[2]+p[1]))
            result=min(result,np.linalg.norm(d)**3/np.linalg.norm(np.cross(d,dd)))
    return result


def curve_spec(rotation_rad=0.,turns=3.):
    """Viewer deformTube-compatible path with the radial start normal."""
    return {'normal':[math.cos(rotation_rad),math.sin(rotation_rad),0.],
            'segments':stored_path(rotation_rad,turns)}
