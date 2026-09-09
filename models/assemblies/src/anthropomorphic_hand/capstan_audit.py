"""Exact three-body clearance plus canonical groove/rope path metrics."""
import json,math
import numpy as np
from lib.capstan import make_capstan,make_terminal_ferrule,make_stored_tendon
from lib.capstan_path import *

def certify_turn_gap():
    """Convex-hull subdivision proves nonlocal, one-revolution turn separation."""
    from lib.capstan_path import _quarter
    def split(p):
        a=(p[:-1]+p[1:])/2;b=(a[:-1]+a[1:])/2;c=(b[0]+b[1])/2
        return np.array([p[0],a[0],b[0],c]),np.array([c,b[1],a[2],p[3]])
    threshold=.790;stack=[(_quarter(0),_quarter(j),0) for j in (3,4,5)];cells=0;least=float('inf')
    while stack:
        a,b,depth=stack.pop();cells+=1
        amin,amax=a.min(axis=0),a.max(axis=0);bmin,bmax=b.min(axis=0),b.max(axis=0)
        gap=np.maximum(0,np.maximum(amin-bmax,bmin-amax));lower=float(np.linalg.norm(gap))
        if lower>=threshold:least=min(least,lower);continue
        if depth>=40:raise AssertionError('turn separation certificate did not converge')
        if np.linalg.norm(amax-amin)>=np.linalg.norm(bmax-bmin):
            x,y=split(a);stack.extend([(x,b,depth+1),(y,b,depth+1)])
        else:
            x,y=split(b);stack.extend([(a,x,depth+1),(a,y,depth+1)])
    return {'centerline_gap_lower_bound_mm':threshold,'surface_gap_lower_bound_mm':threshold-.6,'subdivision_cells':cells,'proof':'Axis-aligned bounds of exact cubic Bezier control hulls; recursive bisection of quarter 0 against quarters 3, 4, 5. Rotational and axial repetition covers every nearest pair of turns. Other azimuth sectors have large radial separation; farther repeated turns have larger axial separation.'}

def run():
    cap,terminal,rope=make_capstan(),make_terminal_ferrule(),make_stored_tendon()
    bodies={'capstan':cap,'terminal':terminal,'rope':rope};pairs=[]
    for i,(an,a) in enumerate(bodies.items()):
        for bn,b in list(bodies.items())[i+1:]:
            common=a&b; volume=common.volume if common else 0
            pairs.append({'a':an,'b':bn,'intersection_mm3':volume,'clear':volume<1e-8})
    full=full_groove_path(); neutral=stored_path()
    # Curvature polynomial rational extremum roots per segment, not just samples.
    minR=float('inf')
    for seg in full:
        p=np.array(seg['points']);d=np.stack([3*(p[1]-p[0]),6*(p[2]-2*p[1]+p[0]),3*(p[3]-3*p[2]+3*p[1]-p[0])],axis=1)
        from numpy.polynomial import polynomial as poly
        A=np.zeros(5)
        for v in d:A[:len(poly.polymul(v,v))]+=poly.polymul(v,v)
        dd=np.stack([d[:,1],2*d[:,2]],axis=1)
        cross=[poly.polysub(poly.polymul(d[(i+1)%3],dd[(i+2)%3]),poly.polymul(d[(i+2)%3],dd[(i+1)%3])) for i in range(3)]
        B=np.zeros(7)
        for v in cross:B[:len(poly.polymul(v,v))]+=poly.polymul(v,v)
        deriv=poly.polysub(3*poly.polymul(poly.polyder(A),B),poly.polymul(A,poly.polyder(B)))
        roots=poly.polyroots(poly.polytrim(deriv,tol=1e-14))
        ts=[0.,1.]+[r.real for r in roots if abs(r.imag)<1e-7 and 0<r.real<1]
        for t in ts:minR=min(minR,math.sqrt(poly.polyval(t,A)**3/poly.polyval(t,B)))
    rotations=[]
    for q in np.linspace(-5*math.pi,5*math.pi,21):
        path=stored_path(float(q));rotations.append({'rotation_rad':float(q),'stored_length_mm':path_length(path),'exit':endpoint(path).tolist(),'tangent':tangent(path).tolist()})
    report={'pairs':pairs,'neutral_stored_length_mm':path_length(neutral),'full_storage_length_mm':path_length(full),'minimum_bend_radius_mm':minR,'rope_radius_mm':.3,'groove_radius_mm':.35,'seated_rope_wall_clearance_mm':.05,'adjacent_turn_certificate':certify_turn_gap(),'adjacent_turn_nominal_axial_surface_gap_mm':.2,'adjacent_turn_note':'The .19 mm certified lower bound is conservative; the actual gap is slightly below the .2 mm nominal axial gap because of helix slope.','rotation_samples':rotations}
    dest='models/assemblies/validation/anthropomorphic_hand/capstan_audit.json';json.dump(report,open(dest,'w'),indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='rotation_samples'},indent=2))
    assert all(p['clear'] for p in pairs)
if __name__=='__main__':run()
