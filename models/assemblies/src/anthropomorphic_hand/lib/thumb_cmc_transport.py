"""C1 fixed-length CMC reaction-liner candidate solver.

MCP-flexion and IP liners use three cubic spans; MCP-abduction liners
use four. The additional free stations let the nested bank move without
changing a pulley, joint range, tendon count, or working length.

Six downstream thumb channels. Exact geometry validation remains separate;
a successful constrained optimization is not itself a collision certificate.
The original +Y inlet tangent has a proven carrier collision at yaw45. The
accepted inlet_angle parameter is a 35-degree fixed parent-frame tilt toward
+X, coordinated with the upstream wrist guide. All endpoint positions are exact.
Carrier/metacarpal ribbon envelopes are conservative swept-curve capsules.
"""
from lib.bowden_mcp import sampled_points,cylinder_sdf
from lib.bowden_universal import _rotate,_length,_curvatures
from lib.thumb_yaw_transport import thumb_yaw_reaction_span
from lib.thumb_cmc_atlas import ATLAS
from scipy.optimize import minimize,brentq
from scipy.spatial import cKDTree
from math import sin,cos,radians,atan2,asin
import numpy as np

MCP_FLEX_OUTLET_Y = 16.

def solve(flex,yaw,lane,others=None,length=40.,initials_extra=None,inlet_angle=35.,only_extra=False,span_count=3,outlet_y=None,diagnostic=None):
 if outlet_y is None:outlet_y=MCP_FLEX_OUTLET_Y
 if not -15<=flex<=65 or not -25<=yaw<=45:raise ValueError("CMC pose outside specified ranges")
 if initials_extra:span_count=max(span_count,max((len(v)-2)//6+1 for v in initials_extra))
 others=[] if others is None else others
 sign=np.sign(lane);special=abs(lane)==4.2
 target_length=length
 f,y=radians(flex)/2,radians(yaw)/2;quat=np.array([cos(y)*cos(f),cos(y)*sin(f),sin(y)*sin(f),sin(y)*cos(f)])
 t0=np.array([sin(radians(inlet_angle)),cos(radians(inlet_angle)),0.]);p0=np.array([lane,-12.25,0.]);p3=_rotate([sign*.9,outlet_y,sign*5.5] if special else [lane,12.25,0.],quat);t1=_rotate([0,1,0],quat)
 def old_cs(v):
  a,b,d,my,mz,theta,mx,psi=v;ya=radians(yaw)/2+psi;tm=np.array([-sin(ya)*cos(theta),cos(ya)*cos(theta),sin(theta)]);m=np.array([(p0[0]+p3[0])/2+mx,my,mz]);return np.array([[p0,p0+a*t0,m-b*tm,m],[m,m+b*tm,p3-d*t1,p3]])
 def cs(v):
  v=np.asarray(v);points=[p0]+[v[i:i+3] for i in range(2,len(v),6)]+[p3]
  handles=[v[0]*t0]+[v[i+3:i+6] for i in range(2,len(v),6)]+[v[1]*t1]
  return np.asarray([[points[i],points[i]+handles[i],points[i+1]-handles[i+1],points[i+1]] for i in range(len(points)-1)])
 def resample_parameters(v):
  if len(v)==2+6*(span_count-1):return np.asarray(v)
  oc=cs(v);old_count=len(oc);ratio=old_count/span_count;out=[v[0]*ratio,v[1]*ratio]
  for j in range(1,span_count):
   u=j*ratio;i=min(int(u),old_count-1);t=u-i;c=oc[i]
   point=(1-t)**3*c[0]+3*(1-t)**2*t*c[1]+3*(1-t)*t*t*c[2]+t**3*c[3]
   handle=ratio*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2]))
   out.extend(point);out.extend(handle)
  return np.asarray(out)
 def elevate(old):
  # Three Hermite spans sampled from the initial two cubics; shared tangents.
  oc=old_cs(old)
  def pv(s):
   i=min(int(s),1);t=s-i;c=oc[i]
   p=(1-t)**3*c[0]+3*(1-t)**2*t*c[1]+3*(1-t)*t*t*c[2]+t**3*c[3]
   v=3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2]))
   return p,v*2/9
  m1,h1=pv(2/3);m2,h2=pv(4/3)
  return np.r_[old[0]*2/3,old[2]*2/3,m1,h1,m2,h2]
 y=radians(yaw);f=radians(flex);rx=np.array([cos(y),sin(y),0]);ry=np.array([-sin(y)*cos(f),cos(y)*cos(f),sin(f)]);rz=np.array([sin(y)*sin(f),-cos(y)*sin(f),cos(f)])
 def dense_bezier(points):
  from scipy.special import comb
  p=np.asarray(points);n=len(p)-1;t=np.linspace(0,1,1601)
  return sum(comb(n,i)*(1-t[:,None])**(n-i)*t[:,None]**i*p[i] for i in range(n+1))
 carrier=[];meta=[]
 for sx in (-1,1):
  x=10.5
  for z in (11.,-15.):
   if z<0:
    points=[(sx*x,2.90,-1.25),(sx*x,4.,-2.5),(sx*x,5.,-9.),(sx*x,9.,-18.),(sx*3.,5.,-16.5),(sx*1.2,1.85,-15.)]
   else:
    points=[(sx*x,-2.90,1.25),(sx*x,-10.7,3.),(sx*5.8,-10.7,14.45),(sx*1.2,-1.85,11.)]
   carrier.extend(dense_bezier(points))
  for z in (12.5,-16.5):
   sn=np.sign(z);x=8.775
   points=[(sx*x,1.1,sn*2.2),(sx*(x-1.5),1.1,sn*2.2),(sx*(x-1.5),7.5,sn*9.5),(sx*x,20.,z+sn*4.5),(sx*7.5,31.,z+sn*4.),(sx*3.14,36.,z+sn*3.),(sx*3.14,36.,z)]
   meta.extend(dense_bezier(points))
 carrier_tree=cKDTree(carrier);meta_tree=cKDTree(meta)
 def obstacles(v):
  p=sampled_points(cs(v),81);out=[]
  for z in[-11.,-13.5]:out.extend(cylinder_sdf(np.linalg.norm(p[:,:2],axis=1)-7.5,np.abs(p[:,2]-z)-.75)-.48)
  xx=p@rx; yy=-p[:,0]*sin(y)+p[:,1]*cos(y);rad=np.sqrt(yy*yy+p[:,2]**2)
  out.extend(rad-1.48)
  for x in[-.9,.9]:out.extend(cylinder_sdf(rad-7.5,np.abs(xx-x)-.75)-.48)
  child=np.column_stack((xx,p@ry,p@rz))
  parent=np.column_stack((xx,yy,p[:,2]))
  out.extend(carrier_tree.query(parent,workers=1)[0]-1.30)
  out.extend(meta_tree.query(child,workers=1)[0]-1.25)
  for side in (-1,1):
   out.extend(cylinder_sdf(np.linalg.norm(parent[:,1:],axis=1)-3.75,np.abs(parent[:,0]-side*10.5)-.95)-.50)
   out.extend(cylinder_sdf(np.linalg.norm(child[:,1:],axis=1)-3.55,np.abs(child[:,0]-side*8.775)-.725)-.50)
  for z in (11.,-15.):
   out.extend(cylinder_sdf(np.linalg.norm(parent[:,:2],axis=1)-2.75,np.abs(parent[:,2]-z)-.70)-.50)
  for z in (12.5,-16.5):
   out.extend(cylinder_sdf(np.linalg.norm(child[:,:2]-[0,36],axis=1)-3.75,np.abs(child[:,2]-z)-1.)-.50)
  return np.array(out)
 cloud=[]
 for s in[-1,1]:
  own=thumb_yaw_reaction_span(yaw,s);cloud.extend(sampled_points([z['points'] for z in own],501));end=np.array(own[-1]['points'][-1]);cloud.extend([end+t*np.array([-sin(y),cos(y),0]) for t in np.linspace(0,3,101)])
 for other in others:cloud.extend(sampled_points(other,501))
 tree=cKDTree(cloud)
 yaw_leads=np.vstack([np.column_stack((np.full(151,-sign*7.),np.linspace(-3.,0.,151),np.full(151,-11. if sign>0 else -13.5))) for sign in(-1,1)])
 yaw_lead_tree=cKDTree(yaw_leads)
 cons=[{'type':'ineq','fun':lambda v:yaw_lead_tree.query(sampled_points(cs(v),241),workers=1)[0]-.81},{'type':'eq','fun':lambda v:_length(cs(v))-target_length},{'type':'ineq','fun':lambda v:1/3.55-_curvatures(cs(v))},{'type':'ineq','fun':obstacles},{'type':'ineq','fun':lambda v:tree.query(sampled_points(cs(v),121),workers=1)[0]-.95}]
 initials=[[5,5,5,3,-7+flex*.075,radians(flex)/2,0,0],[7,5,5,0,-5,0,0,0],[5,5,5,4,4,.8,0,0]]
 halfq=np.array([1+quat[0],*quat[1:]]);halfq/=np.linalg.norm(halfq)
 tmid=_rotate([0,1,0],halfq);normal=_rotate([0,0,1],halfq)
 theta=asin(tmid[2]);psi=atan2(-tmid[0],tmid[1])-radians(yaw)/2
 for handle in[5.,7.,9.]:
  for polarity in[-1,1]:
   def seed(h):
    m=(p0+p3)/2+polarity*h*normal
    return [handle,handle,handle,m[1],m[2],theta,m[0]-(p0[0]+p3[0])/2,psi]
   try:
    h=brentq(lambda h:_length(old_cs(seed(h)))-target_length,.001,30.)
    initials.insert(0,seed(h))
   except ValueError:pass
 best=None
 initials=[elevate(v) for v in initials]
 if initials_extra:initials=list(initials_extra)+( [] if only_extra else initials)
 initials=[resample_parameters(v) for v in initials]
 for initial in initials:
  initial=np.asarray(initial,dtype=float)
  if abs(_length(cs(initial))-target_length)<1e-8 and max(_curvatures(cs(initial)))<1/3.54 and min(obstacles(initial))>-1e-5 and tree.query(sampled_points(cs(initial),501),workers=1)[0].min()>.9499 and yaw_lead_tree.query(sampled_points(cs(initial),501),workers=1)[0].min()>.7999:
   best=initial;break
  res=minimize(lambda v:float(.002*np.sum((v-initial)**2)),initial,bounds=[(.5,16)]*2+[(-30,30)]*(len(initial)-2),method='SLSQP',constraints=cons,options={'maxiter':100,'ftol':1e-9})
  # Finish near-feasible equality residuals with a one-dimensional root;
  # all original radius/obstacle/separation checks still run afterward.
  if 1e-8<abs(_length(cs(res.x))-target_length)<.02:
   base=res.x.copy()
   for coordinate in(0,1):
    def scalar(q):
     v=base.copy();v[coordinate]=q;return _length(cs(v))-target_length
    lo=max(.500001,base[coordinate]-.1);hi=min(15.999999,base[coordinate]+.1)
    if scalar(lo)*scalar(hi)<=0:
     trial=base.copy();trial[coordinate]=brentq(scalar,lo,hi,xtol=1e-13)
     if max(_curvatures(cs(trial)))<1/3.54 and min(obstacles(trial))>-1e-5 and tree.query(sampled_points(cs(trial),501),workers=1)[0].min()>.9499 and yaw_lead_tree.query(sampled_points(cs(trial),501),workers=1)[0].min()>.7999:
      res.x=trial;break
  candidate_ok=abs(_length(cs(res.x))-target_length)<1e-7 and max(_curvatures(cs(res.x)))<1/3.54 and min(obstacles(res.x))>-1e-5 and yaw_lead_tree.query(sampled_points(cs(res.x),501),workers=1)[0].min()>.7999
  if candidate_ok and tree.query(sampled_points(cs(res.x),501),workers=1)[0].min()<=.9499:
   refined=cons[:-1]+[{'type':'ineq','fun':lambda v:tree.query(sampled_points(cs(v),501),workers=1)[0]-.955}]
   base=res.x.copy()
   res=minimize(lambda v:float(.002*np.sum((v-base)**2)),base,bounds=[(.5,16)]*2+[(-30,30)]*(len(initial)-2),method='SLSQP',constraints=refined,options={'maxiter':150,'ftol':1e-10})
  if diagnostic is not None:
   labels=['yaw_drum_upper','yaw_drum_lower','flex_shaft','flex_drum_negative','flex_drum_positive','carrier_ribbons','metacarpal_ribbons','carrier_boss_negative','metacarpal_boss_negative','carrier_boss_positive','metacarpal_boss_positive','yaw_hub_palmar','yaw_hub_dorsal','metacarpal_hub_palmar','metacarpal_hub_dorsal']
   diagnostic({'length':float(_length(cs(res.x))),'radius':float(1/max(_curvatures(cs(res.x)))),'body_gap':float(min(obstacles(res.x))),'body':labels[int(np.argmin(obstacles(res.x)))//(81*len(cs(res.x)))],'neighbor_distance':float(tree.query(sampled_points(cs(res.x),501),workers=1)[0].min()),'parameters':res.x.tolist()})
  if abs(_length(cs(res.x))-target_length)<1e-7 and max(_curvatures(cs(res.x)))<1/3.54 and min(obstacles(res.x))>-1e-5 and tree.query(sampled_points(cs(res.x),501),workers=1)[0].min()>.9499 and yaw_lead_tree.query(sampled_points(cs(res.x),501),workers=1)[0].min()>.7999:best=res.x;break
 if best is None:
  labels=['yaw_drum_upper','yaw_drum_lower','flex_shaft','flex_drum_negative','flex_drum_positive','carrier_ribbons','metacarpal_ribbons','carrier_boss_negative','metacarpal_boss_negative','carrier_boss_positive','metacarpal_boss_positive','yaw_hub_palmar','yaw_hub_dorsal','metacarpal_hub_palmar','metacarpal_hub_dorsal']
  critical=labels[int(np.argmin(obstacles(res.x)))//(81*len(cs(res.x)))]
  raise ValueError((flex,yaw,lane,res.message,_length(cs(res.x)),1/max(_curvatures(cs(res.x))),min(obstacles(res.x)),tree.query(sampled_points(cs(res.x),501),workers=1)[0].min(),critical))
 return cs(best),best



INLET_ANGLE_DEG = 35.
WORKING_LENGTHS = {'ip':36., 'mcp_abduction':36., 'mcp_flexion':40.}
CHANNEL_ORDER = (-3.,3.,-4.2,4.2,-5.4,5.4)


def cmc_inlet_contract():
    """Accepted parent-fixed anchors and their one-mm upstream splice datums."""
    tangent=np.array([sin(radians(INLET_ANGLE_DEG)),cos(radians(INLET_ANGLE_DEG)),0.])
    rows=[]
    for lane in CHANNEL_ORDER:
        joint='mcp_flexion' if abs(lane)==4.2 else 'ip' if abs(lane)==5.4 else 'mcp_abduction'
        sign=1 if lane>0 else -1
        name='thumb_'+joint+('_positive' if sign>0 else '_negative')
        anchor=np.array([lane,-12.25,0.])
        outlet=[sign*.9,MCP_FLEX_OUTLET_Y,sign*5.5] if joint=='mcp_flexion' else [lane,12.25,0.]
        rows.append({'tendon':name,'lane':lane,'working_length':WORKING_LENGTHS[joint],
                     'anchor':anchor.tolist(),'tangent':tangent.tolist(),
                     'splice_point':(anchor-tangent).tolist(),'frame':'cmc_parent',
                     'outlet':outlet,'outlet_tangent':[0.,1.,0.],'outlet_frame':'cmc_child'})
    return rows


def curves_from_parameters(flex_deg,yaw_deg,lane,parameters,inlet_angle=INLET_ANGLE_DEG,outlet_y=None):
    """Regenerate exact FK endpoints; parameters hold only interior geometry."""
    if outlet_y is None:outlet_y=MCP_FLEX_OUTLET_Y
    f,y=radians(flex_deg)/2,radians(yaw_deg)/2
    quat=np.array([cos(y)*cos(f),cos(y)*sin(f),sin(y)*sin(f),sin(y)*cos(f)])
    sign=1 if lane>0 else -1
    p0=np.array([lane,-12.25,0.]);p3=_rotate([sign*.9,outlet_y,sign*5.5] if abs(lane)==4.2 else [lane,12.25,0.],quat)
    t0=np.array([sin(radians(inlet_angle)),cos(radians(inlet_angle)),0.]);t1=_rotate([0,1,0],quat)
    v=np.asarray(parameters);points=[p0]+[v[i:i+3] for i in range(2,len(v),6)]+[p3]
    handles=[v[0]*t0]+[v[i+3:i+6] for i in range(2,len(v),6)]+[v[1]*t1]
    return np.asarray([[points[i],points[i]+handles[i],points[i+1]-handles[i+1],points[i+1]] for i in range(len(points)-1)])



def correct_length(flex_deg,yaw_deg,lane,parameters,working_length,outlet_y=None):
    """Correct handle0 against adaptive quadrature, preserving both endpoints.

    Runtime recipe: regenerate with exact FK, adjust parameters[0], and solve
    length(path)-working_length=0 on the nearest root in(.5,16). This correction
    alone does not certify curvature or collision; the animated gate does that.
    """
    from scipy.integrate import quad
    v=np.asarray(parameters,dtype=float).copy()
    def residual(a):
        v[0]=a
        curves=curves_from_parameters(flex_deg,yaw_deg,lane,v,outlet_y=outlet_y)
        return sum(quad(lambda t:float(np.linalg.norm(3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2])))),0,1,epsabs=2e-12,epsrel=2e-13)[0] for c in curves)-working_length
    a=float(v[0]);ra=residual(a)
    if abs(ra)<2e-12:return v
    for span in(1e-5,1e-4,.001,.01,.1,.5,2.,8.):
        lo=max(.500001,a-span);hi=min(15.999999,a+span)
        if residual(lo)*residual(hi)<=0:
            v[0]=brentq(residual,lo,hi,xtol=1e-13)
            return v
    raise ValueError('No nearby first-handle length correction root')


def thumb_cmc_packet(flex_deg=0.,yaw_deg=0.,atlas_override=None,outlet_y=None):
    """Six route packets; final whole-thumb verification is a separate gate."""
    from scipy.spatial.transform import Rotation
    if outlet_y is None:outlet_y=MCP_FLEX_OUTLET_Y
    atlas=ATLAS if atlas_override is None else atlas_override
    closest=min(atlas,key=lambda row:(row['flex']-flex_deg)**2+(row['yaw']-yaw_deg)**2)
    oldR=Rotation.from_euler('z',closest['yaw'],degrees=True).as_matrix()@Rotation.from_euler('x',closest['flex'],degrees=True).as_matrix()
    newR=Rotation.from_euler('z',yaw_deg,degrees=True).as_matrix()@Rotation.from_euler('x',flex_deg,degrees=True).as_matrix()
    transport=Rotation.from_rotvec(Rotation.from_matrix(newR@oldR.T).as_rotvec()*.5).as_matrix()
    previous={r['lane']:r for r in closest['rows']};done=[];result=[]
    exact=abs(closest['flex']-flex_deg)<1e-10 and abs(closest['yaw']-yaw_deg)<1e-10
    for contract in cmc_inlet_contract():
        lane=contract['lane'];length=contract['working_length'];prior=np.asarray(previous[lane]['params'])
        if abs(lane)==4.2:contract['outlet'][1]=outlet_y
        if exact:parameters=prior.copy()
        else:
            seed=prior.copy()
            for a in range(2,len(seed),3):seed[a:a+3]=transport@seed[a:a+3]
            seeds=[prior,seed] if abs(lane)==3 else [seed,prior]
            _,parameters=solve(float(flex_deg),float(yaw_deg),lane,done,length=length,initials_extra=seeds,outlet_y=outlet_y)
        parameters=correct_length(flex_deg,yaw_deg,lane,parameters,length,outlet_y=outlet_y)
        curves=curves_from_parameters(flex_deg,yaw_deg,lane,parameters,outlet_y=outlet_y);done.append(curves)
        path=[{'kind':'bezier','points':c.tolist()} for c in curves]
        result.append({'tendon':contract['tendon'],'lane':lane,'path':path,'length':length,'working_length':length,'parameters':parameters.tolist(),
                       'inlet':{'point':contract['anchor'],'tangent':contract['tangent'],'frame':'cmc_parent'},
                       'outlet':{'point':curves[-1,-1].tolist(),'tangent':(newR@np.array([0,1,0])).tolist(),'frame':'posed_cmc_child','local_point':contract['outlet']},
                       'reaction':'ideal snug inextensible reaction liner','net_moment_arms':{'thumb_cmc_flexion':0.,'thumb_cmc_abduction':0.},
                       'length_correction':{'parameter_index':0,'bounds':[.5,16.],'equation':'adaptive path length minus working_length equals zero'},
                       'verification':'candidate; full thumb and animation gates required'})
    return result
