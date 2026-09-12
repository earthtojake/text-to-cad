"""Ideal snug, inextensible Bowden reaction liners for upstream joint transport.

Two exactly C1 cubic Bezier spans at constant X. The liner inner radius equals
the tendon radius: ideal zero clearance is essential to exact decoupling.
Length is maintained by a scalar center-bulge solve, not by scaling geometry.
This defines an admissible shape of an ideal flexible inextensible liner;
finite-clearance or elastic-bending behavior is outside this ideal model.
"""
from math import cos, sin, radians, sqrt

ANCHOR_DISTANCE = 12.25
ANCHOR_Z = -6.0
WORKING_LENGTH = 28.5
TENDON_RADIUS = 0.30
LINER_INNER_RADIUS = 0.30
LINER_OUTER_RADIUS = 0.45
LANE_PITCH = 1.20
ANGLE_RANGE = (-25.0, 110.0)
GAUSS_NODES = (0.001368069075259215, 0.007194244227365865, 0.017618872206246805, 0.03254696203113017, 0.051839422116973954, 0.07531619313371501, 0.10275810201602881, 0.13390894062985514, 0.16847786653489238, 0.20614212137961885, 0.24655004553388532, 0.28932436193468236, 0.33406569885893617, 0.38035631887393145, 0.42776401920860174, 0.4758461671561308, 0.5241538328438692, 0.5722359807913983, 0.6196436811260685, 0.6659343011410639, 0.7106756380653176, 0.7534499544661146, 0.7938578786203812, 0.8315221334651076, 0.8660910593701449, 0.8972418979839711, 0.924683806866285, 0.948160577883026, 0.9674530379688698, 0.9823811277937532, 0.9928057557726342, 0.9986319309247408)
GAUSS_WEIGHTS = (0.0035093050047345703, 0.008137197365453142, 0.012696032654630965, 0.01713693145651078, 0.02141794901111345, 0.025499029631188132, 0.02934204673926781, 0.03291111138818085, 0.03617289705442422, 0.039096947893535135, 0.04165596211347343, 0.04382604650220195, 0.04558693934788196, 0.04692219954040224, 0.047819360039637424, 0.04827004425736393, 0.04827004425736393, 0.047819360039637424, 0.04692219954040224, 0.04558693934788196, 0.04382604650220195, 0.04165596211347343, 0.039096947893535135, 0.03617289705442422, 0.03291111138818085, 0.02934204673926781, 0.025499029631188132, 0.02141794901111345, 0.01713693145651078, 0.012696032654630965, 0.008137197365453142, 0.0035093050047345703)


def cubic_point(points,t):
    u=1-t
    return [u*u*u*points[0][i]+3*u*u*t*points[1][i]+3*u*t*t*points[2][i]+t*t*t*points[3][i] for i in range(3)]


def cubic_derivative(points,t):
    u=1-t
    return [3*(u*u*(points[1][i]-points[0][i])+2*u*t*(points[2][i]-points[1][i])+t*t*(points[3][i]-points[2][i])) for i in range(3)]


def cubic_length(points):
    return sum(w*sqrt(sum(v*v for v in cubic_derivative(points,t))) for t,w in zip(GAUSS_NODES,GAUSS_WEIGHTS))


def _curves(angle_deg,bulge,lane_x):
    q=radians(angle_deg); c,s=cos(q),sin(q)
    half=q/2; ch,sh=cos(half),sin(half)
    t=max(0.0,min(1.0,(-angle_deg-15)/10)); blend=t*t*(3-2*t)
    a=7.0-.09*blend; b=7.0-1.45*blend
    p0=[lane_x,-ANCHOR_DISTANCE,ANCHOR_Z]
    p3=[lane_x,ANCHOR_DISTANCE*c-ANCHOR_Z*s,ANCHOR_DISTANCE*s+ANCHOR_Z*c]
    middle=[lane_x,(p0[1]+p3[1])/2-bulge*sh,(p0[2]+p3[2])/2+bulge*ch]
    first=[p0,[lane_x,p0[1]+a,p0[2]], [lane_x,middle[1]-b*ch,middle[2]-b*sh],middle]
    second=[middle,[lane_x,middle[1]+b*ch,middle[2]+b*sh],[lane_x,p3[1]-a*c,p3[2]-a*s],p3]
    return [first,second]


def bowden_crossover(angle_deg=0.0,lane_x=0.0):
    if not ANGLE_RANGE[0] <= angle_deg <= ANGLE_RANGE[1]:
        raise ValueError(f'angle {angle_deg} outside validated range {ANGLE_RANGE}')
    lo,hi=-25.0,-1.0
    def length(h):
        return sum(cubic_length(p) for p in _curves(angle_deg,h,lane_x))
    if not length(lo)>WORKING_LENGTH>length(hi):
        raise ValueError('constant-length Bowden branch is not bracketed')
    for _ in range(45):
        mid=(lo+hi)/2
        if length(mid)>WORKING_LENGTH:
            lo=mid
        else:
            hi=mid
    h=(lo+hi)/2; curves=_curves(angle_deg,h,lane_x)
    return {'path':[{'kind':'bezier','points':p} for p in curves],
            'length':sum(cubic_length(p) for p in curves),'bulge':h,
            'inlet':{'point':curves[0][0],'tangent':[0.0,1.0,0.0],'frame':'parent'},
            'outlet':{'point':curves[-1][-1],'tangent':[0.0,cos(radians(angle_deg)),sin(radians(angle_deg))],'frame':'child'},
            'reaction':'ideal snug inextensible liner; net generalized tendon+liner torque zero',
            'net_moment_arm_about_crossed_joint':0.0,
            'minimum_design_radius':3.5}
