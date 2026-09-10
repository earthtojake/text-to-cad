"""Numerical polynomial curvature extrema + independent quadrature validation."""
import json
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial as P
from scipy.integrate import quad
from lib.bowden_transport import (bowden_crossover,cubic_point,cubic_derivative,
    WORKING_LENGTH,LANE_PITCH,LINER_OUTER_RADIUS)


def real_roots(poly):
    return [float(r.real) for r in poly.roots() if abs(r.imag)<1e-7 and 0<r.real<1]


def metrics(points):
    controls=np.asarray(points)
    pos=[P([controls[0,i],3*(controls[1,i]-controls[0,i]),
            3*(controls[2,i]-2*controls[1,i]+controls[0,i]),
            controls[3,i]-3*controls[2,i]+3*controls[1,i]-controls[0,i]]) for i in range(3)]
    u=[p.deriv() for p in pos]; v=[p.deriv() for p in u]
    cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    numerator=sum(p*p for p in cross); speed2=sum(p*p for p in u)
    # d(N/S^3)=0 reduces to N'*S-3*N*S'=0, keeping degree modest.
    critical=numerator.deriv()*speed2-3*numerator*speed2.deriv()
    candidates=[0.0,1.0]+real_roots(critical)
    maximum=max(float(numerator(t)/speed2(t)**3) for t in candidates)
    min_radius=1/np.sqrt(maximum) if maximum>0 else float('inf')
    length,error=quad(lambda t:np.sqrt(float(speed2(t))),0,1,epsabs=1e-11,epsrel=1e-12)
    low=[];high=[]
    for p in pos:
        vals=[float(p(t)) for t in [0,1]+real_roots(p.deriv())]
        low.append(min(vals));high.append(max(vals))
    return {'minimum_radius':float(min_radius),'length':length,'integration_error':error,'minimum':low,'maximum':high}


if __name__=='__main__':
    angles=sorted(set([-25.0,110.0]+list(np.arange(-25,111,10))+list(np.linspace(-25,110,51))))
    rows=[];low=np.array([np.inf]*3);high=-low.copy()
    for q in angles:
        route=bowden_crossover(float(q)); ms=[metrics(s['points']) for s in route['path']]
        p0,p1=[s['points'] for s in route['path']]
        join_position=np.linalg.norm(np.array(p0[-1])-p1[0])
        join_tangent=np.linalg.norm(np.array(cubic_derivative(p0,1))-cubic_derivative(p1,0))
        length=sum(m['length'] for m in ms); radius=min(m['minimum_radius'] for m in ms)
        for m in ms:
            low=np.minimum(low,m['minimum']);high=np.maximum(high,m['maximum'])
        rows.append({'angle_deg':float(q),'length_mm':length,'length_error_mm':abs(length-WORKING_LENGTH),
                     'minimum_radius_mm':radius,'join_position_error_mm':float(join_position),
                     'join_derivative_error':float(join_tangent),
                     'clear_radius_and_length':bool(radius>=3.5 and abs(length-WORKING_LENGTH)<1e-8 and join_tangent<1e-10)})
    output={'status':'local routing gate only; full hand solid collisions remain required',
            'working_length_mm':WORKING_LENGTH,'minimum_radius_mm':min(r['minimum_radius_mm'] for r in rows),
            'maximum_length_error_mm':max(r['length_error_mm'] for r in rows),
            'sample_count':len(rows),'rows':rows,
            'centerline_envelope_at_samples':{'minimum':low.tolist(),'maximum':high.tolist()},
            'liner_lane_pitch_mm':LANE_PITCH,'liner_outer_radius_mm':LINER_OUTER_RADIUS,
            'exact_interlane_clearance_mm':LANE_PITCH-2*LINER_OUTER_RADIUS,
            'interlane_proof':'All paths are identical translations at constant X. Point distance is at least absolute X separation. Matching parameter points attain that bound.',
            'curvature_method':'Stationary points of squared curvature rational polynomial plus endpoints; independent adaptive arclength quadrature.',
            'reaction_assumption':'An ideally flexible inextensible zero-clearance liner carries equal and opposite compressive reaction; tendon plus liner work at crossed joint is T*dL=0. No positive clearance, liner bending stiffness or friction is silently assumed.',
            'excluded':'Anchor fasteners and their mounts, finite-clearance construction, actual passive elastic equilibrium, and hand-body collisions.'}
    Path(__file__).with_name('bowden_transport_report.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k!='rows'},indent=2))
    if not all(r['clear_radius_and_length'] for r in rows):raise SystemExit(1)
