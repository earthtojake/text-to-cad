"""Universal MCP reaction liner constrained around actual pulley and shaft volumes.

Inlet and outlet anchors are Y±12.25 in their respective rigid frames.
Fixed working length is 30 mm. Yaw drums occupy Z−9.5 and Z−12.
This optimizer is a geometric candidate generator; full assembly checks are
separate and can reject an individually feasible path.
"""
from functools import lru_cache
from math import cos,sin,radians
import numpy as np
from scipy.optimize import minimize,brentq
from scipy.integrate import quad
from scipy.spatial import cKDTree
from lib.yaw_transport import yaw_reaction_span
from lib.bowden_universal import _rotate,_length,_curvatures

INLET_DISTANCE=12.25
OUTLET_DISTANCE=12.25
WORKING_LENGTH=30.
ENVELOPE=.48  # .45 liner plus .03 sampling reserve
DESIGN_RADIUS=3.65


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
    return np.array([[p0,p0+[0,a,0],middle-b*tm,middle],
                     [middle,middle+b*tm,p3-d*t1,p3]])


def sampled_points(cs,count=121):
    t=np.linspace(0,1,count)[None,:,None];c=np.asarray(cs)[:,None,:,:]
    return ((1-t)**3*c[:,:,0]+3*(1-t)**2*t*c[:,:,1]+3*(1-t)*t*t*c[:,:,2]+t**3*c[:,:,3]).reshape(-1,3)


def cylinder_sdf(radial,axial):
    return np.sqrt(np.maximum(radial,0)**2+np.maximum(axial,0)**2)+np.minimum(np.maximum(radial,axial),0)


def obstacle_clearances(points,yaw_deg,envelope=ENVELOPE):
    p=np.asarray(points);results=[]
    # Turned yaw drums: maximum radius6 and half width.75.
    for sign in (-1,1):
        results.append(cylinder_sdf(np.linalg.norm(p[:,:2],axis=1)-6.,np.abs(p[:,2]-(-9.5 if sign>0 else -12))-.75)-envelope)
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
def solve_mcp(flex_deg,yaw_deg,lane,cheek_inner=7.55,cheek_margin=.75):
    if not -15<=flex_deg<=90 or not -25<=yaw_deg<=25:
        raise ValueError('MCP solve outside declared finger ranges')
    target_length=WORKING_LENGTH
    cs=lambda v:curves(flex_deg,yaw_deg,lane,v)
    cons=[{'type':'eq','fun':lambda v:_length(cs(v))-target_length},
          {'type':'ineq','fun':lambda v:1/DESIGN_RADIUS-_curvatures(cs(v))},
          {'type':'ineq','fun':lambda v:obstacle_clearances(sampled_points(cs(v)),yaw_deg)}]
    # The proximal phalanx's inner cheeks begin at X±7.55. Keep the
    # entire liner inside that physical corridor, including between samples.
    # This rejects feasible-but-outboard optimization branches that intersect
    # a bearing cheek even though they clear the isolated drums.
    y=radians(yaw_deg);child_x=np.array([cos(y),sin(y),0.])
    f=radians(flex_deg)
    child_y=np.array([-sin(y)*cos(f),cos(y)*cos(f),sin(f)])
    child_z=np.array([sin(y)*sin(f),-cos(y)*sin(f),cos(f)])
    def cheek_corridor(points):
        return (cheek_inner-cheek_margin)+1.5*np.maximum(-4.-points@child_y,0)+1.5*np.maximum(np.abs(points@child_z)-5.2,0)-np.abs(points@child_x)
    cons.append({'type':'ineq','fun':lambda v:cheek_corridor(sampled_points(cs(v),401))})
    other_cloud=[]
    for sign in (-1,1):
        own=yaw_reaction_span(yaw_deg,sign)
        other_cloud.extend(sampled_points([s['points'] for s in own],801))
        end=np.array(own[-1]['points'][-1]);q=radians(yaw_deg)
        direction=np.array([-sin(q),cos(q),0.])
        other_cloud.extend([end+t*direction for t in np.linspace(0,3,151)])
    own_tree=cKDTree(np.array(other_cloud))
    cons.append({'type':'ineq','fun':lambda v:own_tree.query(sampled_points(cs(v),401),workers=1)[0]-1.02})
    outer_parameters=None
    if abs(lane)<3.5:
        outer_parameters=solve_mcp(flex_deg,yaw_deg,float(np.sign(lane)*4.2),cheek_inner,cheek_margin)
        outer_cloud=sampled_points(curves(flex_deg,yaw_deg,float(np.sign(lane)*4.2),outer_parameters),601)
        outer_tree=cKDTree(outer_cloud)
        cons.append({'type':'ineq','fun':lambda v:outer_tree.query(sampled_points(cs(v),241),workers=1)[0]-1.02})
    initials=[[5,5,5,4,-4+.065*flex_deg,.5],
              [5,5,5,6,1,1.0],
              [7,5,4,2,-5,.2],
              [4,5,3,7,4,1.3]]
    initials=[v+[offset,0.] for offset in (0.,2.*np.sign(lane),-2.*np.sign(lane)) for v in initials]
    if outer_parameters is not None:
        initials.insert(0,list(outer_parameters))
        for advance in (1.0,2.5,4.):
            seed=list(outer_parameters);seed[3]+=advance;seed[6]=0.;seed[7]=-radians(yaw_deg)/2
            initials.insert(0,seed)
    def candidates():
        yield from initials
        if abs(yaw_deg)>1e-6:
            # Continue a solved neighbouring yaw configuration only when
            # direct seeds fail. This leaves all accepted direct solutions
            # unchanged and follows a feasible branch into extreme poses.
            neighbour=yaw_deg-np.sign(yaw_deg)*min(5.,abs(yaw_deg))
            try:yield solve_mcp(flex_deg,float(neighbour),lane,cheek_inner,cheek_margin)
            except ValueError:pass
    best=None
    for initial in candidates():
        result=minimize(lambda v:float(.02*np.sum((v[:3]-5)**2)+.001*((v[3]-4)**2+(v[4]+1)**2)+.008*v[6]**2+.03*v[7]**2),np.asarray(initial,dtype=float),
                        bounds=[(.5,17)]*3+[(-13,18),(-18,20),(-1.5,3)]+([(0,0),(0,0)] if flex_deg==0 and yaw_deg==0 else [(-10,10),(-1.5,1.5)]),constraints=cons,
                        method='SLSQP',options={'maxiter':500,'ftol':1e-10})
        if (abs(_length(cs(result.x))-target_length)<1e-8
                and _curvatures(cs(result.x)).max()<1/3.64
                and cheek_corridor(sampled_points(cs(result.x),801)).min() < -1e-5):
            # The finite cheek envelope has piecewise-linear corners. A
            # coarse curve sample may miss its narrowest approach; tighten
            # that candidate against a denser sample with added margin.
            result=minimize(lambda v:float(.02*np.sum((v[:3]-5)**2)+.001*((v[3]-4)**2+(v[4]+1)**2)+.008*v[6]**2+.03*v[7]**2),result.x,
                            bounds=[(.5,17)]*3+[(-13,18),(-18,20),(-1.5,3),(-10,10),(-1.5,1.5)],
                            constraints=cons+[{'type':'ineq','fun':lambda v:cheek_corridor(sampled_points(cs(v),1601))-.02}],
                            method='SLSQP',options={'maxiter':200,'ftol':1e-11})
        valid=abs(_length(cs(result.x))-target_length)<1e-8 and _curvatures(cs(result.x)).max()<1/3.64 and obstacle_clearances(sampled_points(cs(result.x)),yaw_deg).min()>-1e-6
        if valid:
            valid=cheek_corridor(sampled_points(cs(result.x),801)).min()>=-1e-5
        if valid:
            valid=own_tree.query(sampled_points(cs(result.x),801),workers=1)[0].min()>=1.01999
        if valid and outer_parameters is not None:
            valid=outer_tree.query(sampled_points(cs(result.x),241),workers=1)[0].min()>=1.01999
        if valid:
            best=result.x;break
    if best is None and cheek_margin > .60:
        # The primary corridor reserves .30 mm beyond the actual .45 mm
        # liner radius. At a compound corner, retain a .15 mm reserve and
        # re-solve; exact CAD distances still decide geometric acceptance.
        return solve_mcp(flex_deg,yaw_deg,lane,cheek_inner,.60)
    if best is None:
        raise ValueError(f'MCP routing failed flex={flex_deg}, yaw={yaw_deg}, lane={lane}: {result.message}; L={_length(cs(result.x))}, R={1/_curvatures(cs(result.x)).max()}, obstacle={obstacle_clearances(sampled_points(cs(result.x)),yaw_deg).min()}, own_gap={own_tree.query(sampled_points(cs(result.x),801),workers=1)[0].min()}, cheek={cheek_corridor(sampled_points(cs(result.x),801)).min()}')
    # Refine against independent adaptive quadrature, so numerical optimizer
    # equality residuals cannot masquerade as upstream tendon moment arms.
    def refined_length(a):
        v=best.copy();v[0]=a
        total=0.
        for c in cs(v):
            total+=quad(lambda t:float(np.linalg.norm(3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2])))),0,1,epsabs=2e-12,epsrel=2e-13)[0]
        return total-target_length
    best[0]=brentq(refined_length,best[0]-1e-4,best[0]+1e-4,xtol=1e-13)
    return tuple(float(v) for v in best)


def mcp_crossover(flex_deg=0.,yaw_deg=0.,lane=3.,cheek_inner=7.55):
    parameters=solve_mcp(float(flex_deg),float(yaw_deg),float(lane),float(cheek_inner));cs=curves(flex_deg,yaw_deg,lane,parameters)
    p0,p3,t1=datums(flex_deg,yaw_deg,lane)
    return {'path':[{'kind':'bezier','points':p.tolist()} for p in cs],
            'parameters':list(parameters),'length':_length(cs),
            'inlet':{'point':p0.tolist(),'tangent':[0,1,0],'frame':'parent'},
            'outlet':{'point':p3.tolist(),'tangent':t1.tolist(),'frame':'child'},
            'net_moment_arms':{'flexion':0.,'abduction':0.}}
