"""Recognize actual stored-rope curves as prefixes of a proven native envelope."""
import math
import numpy as np
from lib.capstan_path import full_groove_path

def split_left(points,t):
    p=np.asarray(points,float);a=(1-t)*p[:-1]+t*p[1:];b=(1-t)*a[:-1]+t*a[1:];c=(1-t)*b[0]+t*b[1]
    return np.array([p[0],a[0],b[0],c])

def verify_prefix(route,tendon):
    groups=[g for g in route['groups'] if g.get('guide')=='capstan']
    assert len(groups)==1 and groups[0]['label']==route['name']+'_capstan_wrap'
    q=route['capstan_rotation'];assert abs(q)<=5*math.pi+1e-12
    path=groups[0]['path'];full=full_groove_path();assert 1<=len(path)<=len(full)
    basis=np.diag([tendon['sign'],1.,tendon['sign']]);origin=np.asarray(tendon['capstan_center'])
    c,s=math.cos(q),math.sin(q);rotation=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    error=0.;last_parameter=1.
    for index,segment in enumerate(path):
        assert segment['kind']=='bezier' and len(segment['points'])==4
        actual=(np.asarray(segment['points'])-origin)@basis@rotation
        expected=np.asarray(full[index]['points'])
        if index==len(path)-1:
            direction=expected[1]-expected[0]
            t=float(np.dot(actual[1]-expected[0],direction)/np.dot(direction,direction))
            assert -1e-12<t<=1.+1e-12
            last_parameter=t;expected=split_left(expected,t)
        error=max(error,float(np.max(np.abs(actual-expected))))
    assert error<1e-10,('stored path is not an envelope prefix',route['name'],error)
    return dict(tendon=route['name'],rotation_rad=q,segments=len(path),last_segment_parameter=last_parameter,maximum_control_point_residual_mm=error,method='inverse physical placement and spool rotation; exact cubic prefixes with final de Casteljau subdivision')
