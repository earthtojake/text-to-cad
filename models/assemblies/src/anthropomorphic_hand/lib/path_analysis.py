"""Analytic extrema for cubic tendon curves; no CAD kernel dependency."""
import numpy as np
from numpy.polynomial import Polynomial as P
from lib.bowden_transport import cubic_length
from lib.axis_transport import segment_length, point_at


def cubic_polynomials(points):
    p = np.asarray(points, dtype=float)
    return [P([p[0,i], 3*(p[1,i]-p[0,i]),
               3*(p[2,i]-2*p[1,i]+p[0,i]),
               p[3,i]-3*p[2,i]+3*p[1,i]-p[0,i]]) for i in range(3)]


def real_unit_roots(poly):
    return [float(r.real) for r in poly.roots() if abs(r.imag)<1e-7 and 0<r.real<1]


def cubic_min_radius(points):
    p = cubic_polynomials(points)
    u = [x.deriv() for x in p]
    v = [x.deriv() for x in u]
    cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    n = sum(x*x for x in cross)
    s = sum(x*x for x in u)
    stationary = n.deriv()*s - 3*n*s.deriv()
    ts = [0.,1.] + real_unit_roots(stationary)
    maximum = max(float(n(t)/s(t)**3) for t in ts)
    return 1/np.sqrt(maximum) if maximum>1e-20 else float('inf')


def cubic_axis_distance(points, origin=(0,0,0), axis=(1,0,0)):
    p = cubic_polynomials(np.asarray(points)-np.asarray(origin))
    a = np.asarray(axis,dtype=float); a /= np.linalg.norm(a)
    dot = sum(p[i]*a[i] for i in range(3))
    squared = sum(x*x for x in p)-dot*dot
    ts = [0.,1.] + real_unit_roots(squared.deriv())
    return np.sqrt(max(0., min(float(squared(t)) for t in ts)))


def path_length(path):
    return sum(cubic_length(s['points']) if s['kind']=='bezier' else segment_length(s) for s in path)


def path_min_radius(path):
    return min(cubic_min_radius(s['points']) if s['kind']=='bezier' else
               float(np.linalg.norm(np.asarray(s['start'])-s['center'])) if s['kind']=='arc' else
               float('inf') for s in path)


def sample_path(path, maximum_step=.1):
    """Samples with a conservative bound on the distance between samples.

    Cubic derivative norm is bounded by three times the longest control edge.
    This permits a distance lower bound by subtracting maximum_step from a
    nearest sample-pair distance (half a step for each of the two curves).
    """
    points=[]
    for segment in path:
        if segment['kind']=='bezier':
            p=np.asarray(segment['points'])
            n=max(1,int(np.ceil(3*np.linalg.norm(np.diff(p,axis=0),axis=1).max()/maximum_step)))
            t=np.linspace(0,1,n+1)[:,None]
            values=(1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]
        else:
            n=max(1,int(np.ceil(segment_length(segment)/maximum_step)))
            values=np.asarray([point_at(segment,t) for t in np.linspace(0,1,n+1)])
        points.extend(values if not points else values[1:])
    return np.asarray(points)
