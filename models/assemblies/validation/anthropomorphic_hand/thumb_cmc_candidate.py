import sys
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.bowden_mcp import sampled_points,cylinder_sdf
from lib.bowden_universal import _rotate,_length,_curvatures
from lib.thumb_yaw_transport import thumb_yaw_reaction_span
from scipy.optimize import minimize,brentq
from scipy.spatial import cKDTree
from math import sin,cos,radians,atan2,asin
import numpy as np

def solve(flex,yaw,lane,others=[]):
 sign=np.sign(lane);special=abs(lane)==4.2
 target_length=35.5 if special else 33.
 f,y=radians(flex)/2,radians(yaw)/2;quat=np.array([cos(y)*cos(f),cos(y)*sin(f),sin(y)*sin(f),sin(y)*cos(f)])
 p0=np.array([lane,-12.25,0.]);p3=_rotate([sign*.9,13.,sign*5.5] if special else [lane,12.25,0.],quat);t1=_rotate([0,1,0],quat)
 def cs(v):
  a,b,d,my,mz,theta,mx,psi=v;ya=radians(yaw)/2+psi;tm=np.array([-sin(ya)*cos(theta),cos(ya)*cos(theta),sin(theta)]);m=np.array([(p0[0]+p3[0])/2+mx,my,mz]);return np.array([[p0,p0+[0,a,0],m-b*tm,m],[m,m+b*tm,p3-d*t1,p3]])
 y=radians(yaw);f=radians(flex);rx=np.array([cos(y),sin(y),0]);ry=np.array([-sin(y)*cos(f),cos(y)*cos(f),sin(f)]);rz=np.array([sin(y)*sin(f),-cos(y)*sin(f),cos(f)])
 def obstacles(v):
  p=sampled_points(cs(v),201);out=[]
  for z in[-11.,-13.5]:out.extend(cylinder_sdf(np.linalg.norm(p[:,:2],axis=1)-7.5,np.abs(p[:,2]-z)-.75)-.48)
  xx=p@rx; yy=-p[:,0]*sin(y)+p[:,1]*cos(y);rad=np.sqrt(yy*yy+p[:,2]**2)
  out.extend(rad-1.48)
  for x in[-.9,.9]:out.extend(cylinder_sdf(rad-7.5,np.abs(xx-x)-.75)-.48)
  child=np.column_stack((xx,p@ry,p@rz))
  for side in[-1,1]:
   center=np.array([side*8.775,18.,0]);half=np.array([.725,21.55,4.85]);delta=np.abs(child-center)-half
   out.extend(np.linalg.norm(np.maximum(delta,0),axis=1)+np.minimum(np.max(delta,axis=1),0)-.5)
  return np.array(out)
 cloud=[]
 for s in[-1,1]:
  own=thumb_yaw_reaction_span(yaw,s);cloud.extend(sampled_points([z['points'] for z in own],501));end=np.array(own[-1]['points'][-1]);cloud.extend([end+t*np.array([-sin(y),cos(y),0]) for t in np.linspace(0,3,101)])
 for other in others:cloud.extend(sampled_points(other,501))
 tree=cKDTree(cloud)
 cons=[{'type':'eq','fun':lambda v:_length(cs(v))-target_length},{'type':'ineq','fun':lambda v:1/3.65-_curvatures(cs(v))},{'type':'ineq','fun':obstacles},{'type':'ineq','fun':lambda v:tree.query(sampled_points(cs(v),301),workers=1)[0]-1.04}]
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
    h=brentq(lambda h:_length(cs(seed(h)))-target_length,.001,30.)
    initials.insert(0,seed(h))
   except ValueError:pass
 best=None
 for initial in initials:
  res=minimize(lambda v:float(.02*np.sum((v[:3]-5)**2)+.001*((v[3]-3)**2+(v[4]+1)**2)+.008*v[6]**2+.03*v[7]**2),initial,bounds=[(.5,17)]*3+[(-13,18),(-20,20),(-1.5,3),(-10,10),(-1.5,1.5)],method='SLSQP',constraints=cons,options={'maxiter':350,'ftol':1e-9})
  if abs(_length(cs(res.x))-target_length)<1e-7 and max(_curvatures(cs(res.x)))<1/3.6 and min(obstacles(res.x))>-1e-5 and tree.query(sampled_points(cs(res.x),501),workers=1)[0].min()>1.0399:best=res.x;break
 if best is None:raise ValueError((flex,yaw,lane,res.message,_length(cs(res.x)),1/max(_curvatures(cs(res.x))),min(obstacles(res.x))))
 return cs(best)

for f,y in[(0,45),(-15,-25),(65,45)]:
 done=[]
 for lane in[-5.4,5.4,-4.2,4.2,-3.,3.]:
  try:
   p=solve(f,y,lane,done);done.append(p);print('PASS',f,y,lane,flush=True)
  except Exception as e:print('FAIL',e,flush=True);break
