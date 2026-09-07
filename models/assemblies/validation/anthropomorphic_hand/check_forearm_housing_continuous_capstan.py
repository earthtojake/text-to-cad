"""Conservative Bernstein bound for every q in the full ±5π capstan range."""
import sys,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import read_step
from lib.capstan_path import _quarter
from lib.layout import TENDONS
HERE=Path(__file__).resolve().parent
def leaves(n):return [s for c in n.children for s in leaves(c)] if n.children else [n]
p=_quarter(0)[:,:2];d=3*np.diff(p,axis=0)
# Dot(p,p') is degree5; all its values lie in the convex hull of these
# Bernstein coefficients. Both curves stay in a single signed quadrant.
coeff=[sum(math.comb(3,i)*math.comb(2,k-i)/math.comb(5,k)*np.dot(p[i],d[k-i]) for i in range(max(0,k-2),min(3,k)+1)) for k in range(6)]
point_norm_min=min(v.sum() for v in p)/math.sqrt(2)
tangent_norm_min=min(-v[0]+v[1] for v in d)/math.sqrt(2)
radial_tangent_bound=max(map(abs,coeff))/(point_norm_min*tangent_norm_min)
control_radius=max(np.linalg.norm(v) for v in p)
# Exit azimuth is fixed at +X; the longest external control lever is15mm.
x_bound=max(max(abs(t['actuator_center'][0]) for t in TENDONS)+control_radius+15*radial_tangent_bound,max(abs(t['bundle_lane']) for t in TENDONS))
z_min=33.-2.4
rows=[]
for s in leaves(read_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_housing_review.step')):
    b=s.bounding_box();xmin=min(abs(b.min.X),abs(b.max.X)) if b.min.X*b.max.X>0 else 0.
    zmax=max(abs(b.min.Z),abs(b.max.Z))
    clearance=max(xmin-x_bound,z_min-zmax)-.30
    rows.append({'body':s.label,'continuous_surface_clearance_lower_bound_mm':clearance})
report={'ok':all(r['continuous_surface_clearance_lower_bound_mm']>0 for r in rows),'rotation_range_rad':[-5*math.pi,5*math.pi],
        'route_count':48,'bernstein_dot_coefficients':coeff,'radial_unit_tangent_bound':radial_tangent_bound,
        'forearm_control_abs_x_max':x_bound,'forearm_control_abs_z_min':z_min,
        'minimum_surface_clearance_bound_mm':min(r['continuous_surface_clearance_lower_bound_mm'] for r in rows),'bodies':rows,
        'scope':'Entire stored helix and external forearm lead/trunk at every rotation in range; wrist and hand spans are checked separately.'}
(HERE/'forearm_housing_continuous_capstan.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='bodies'}));sys.exit(0 if report['ok'] else 1)
