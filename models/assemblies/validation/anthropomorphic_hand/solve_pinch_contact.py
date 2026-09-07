"""Pad-contact pose candidate; collision/routing gates remain independent."""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from lib.layout import assembled_transforms,JOINT_BY_NAME,FINGERS,THUMB_CMC,THUMB_DIRECTION,finger_fan_matrix

names=['index_mcp_abduction','index_mcp_flexion','index_pip','index_dip','thumb_mcp_abduction','thumb_mcp_flexion','thumb_ip','thumb_cmc_abduction','thumb_cmc_flexion']
fixed={}
start=np.array([-12.,65.,50.,20.,-5.,15.,45.,-15.,50.])
finger=FINGERS[0]
ip=finger_fan_matrix(finger)@np.array([finger.x,finger.base_y+sum(finger.lengths[:2])+.71*finger.lengths[2],5.4,1.])
tp=np.array([*(np.array(THUMB_CMC)+np.array(THUMB_DIRECTION)*(63.+.71*21.)),1.]);tp[2]=5.4
def contact(values):
    pose={**fixed,**dict(zip(names,map(float,values[:9])))};fk=assembled_transforms(pose)
    a=fk['index_dip'];b=fk['thumb_ip'];p=(a@ip)[:3];q=(b@tp)[:3]
    ni=a[:3,:3]@np.array([0.,0.,1.]);nt=b[:3,:3]@np.array([0.,0.,1.])
    theta,phi=values[9:];n=np.array([np.sin(theta)*np.cos(phi),np.sin(theta)*np.sin(phi),np.cos(theta)])
    r45=np.array([[2**-.5,-2**-.5,0],[2**-.5,2**-.5,0],[0,0,1.]])
    ri=a[:3,:3]@finger_fan_matrix(finger)[:3,:3];rt=b[:3,:3]@r45
    qi=ri@np.diag([6.25**2,6.5**2,2.**2])@ri.T;qt=rt@np.diag([6.75**2,7.**2,2.**2])@rt.T
    pi=p+qi@n/np.sqrt(n@qi@n);pt=q-qt@n/np.sqrt(n@qt@n)
    return pose,pi,pt,float(ni@n),float(-nt@n),n
def residual(values):
    pose,p,q,ci,ct,n=contact(values)
    return np.r_[p-q-1e-4*n,20*min(0,ci-.35),20*min(0,ct-.35),.0003*(values[:9]-start)]
lo=[JOINT_BY_NAME[n].limits[0] for n in names]+[0.,-np.pi];hi=[JOINT_BY_NAME[n].limits[1] for n in names]+[np.pi,np.pi]
results=[]
for theta,phi in [(1.5,3.),(1.5,-3.),(2.4,2.8),(.7,2.8),(2.4,-2.8)]:
    initial=np.r_[start,theta,phi]
    results.append(least_squares(residual,np.maximum(lo,np.minimum(hi,initial)),bounds=(lo,hi),max_nfev=400,xtol=1e-12,ftol=1e-12,gtol=1e-12))
result=min(results,key=lambda r:np.linalg.norm(residual(r.x)))
pose,p,q,ci,ct,n=contact(result.x)
report={'pose':pose,'pad_contact_points_mm':[p.tolist(),q.tolist()],'surface_gap_mm':float(np.linalg.norm(p-q)),'palmar_contact_normal_cosines':[ci,ct],'pad_native_ellipsoids':{'center_y_fraction':.71,'center_z_mm':5.4,'index_radii_mm':[6.25,6.5,2.],'thumb_radii_mm':[6.75,7.,2.]},'scope':'Ellipsoidal pad contact candidate only; native pads must match this interface and all actual solids/routes must clear.'}
Path(__file__).with_name('pinch_contact_candidate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
