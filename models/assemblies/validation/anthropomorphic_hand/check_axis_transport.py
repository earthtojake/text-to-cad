"""Certified spatial distance bounds at the requested angular samples.

Run with PYTHONPATH=models/assemblies/src/anthropomorphic_hand.
Uses scipy only for exact nearest sampled point queries; the route is stdlib.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from lib.axis_transport import (crossover, sample_path, point_at, tangent_at,
    array_envelope, GUIDE_OUTER_RADIUS, TENDON_RADIUS, STATION_PITCH)


def samples(limits):
    lo,hi=limits
    stepped=list(np.arange(lo,hi+1e-8,10.0))+[hi]
    return sorted(set(round(float(x),10) for x in stepped+list(np.linspace(lo,hi,51))))


def check_case(count, limits, pitch):
    worst=float('inf'); worstq=None; max_error=0.0; lengths=[]
    # Translation invariance means only separations 1..count-1 are distinct.
    for q in samples(limits):
        routes=[crossover(i,count,q,limits,pitch=pitch) for i in range(count)]
        clouds=[]; spacings=[]
        for route in routes:
            pts,h=sample_path(route['path'],maximum_step=.025)
            clouds.append(np.array(pts)); spacings.append(h); lengths.append(route['length'])
            for left,right in zip(route['path'],route['path'][1:]):
                error=np.linalg.norm(np.array(point_at(left,1))-point_at(right,0))
                error=max(error,np.linalg.norm(np.array(tangent_at(left,1))-tangent_at(right,0)))
                max_error=max(max_error,float(error))
        tree=cKDTree(clouds[0])
        for j in range(1,count):
            sampled=float(tree.query(clouds[j],workers=1)[0].min())
            lower=sampled-(spacings[0]+spacings[j])/2
            if lower<worst: worst,worstq=lower,q
    return {'channels':count,'angle_range_deg':limits,'angle_samples':len(samples(limits)),
            'pitch_mm':pitch,'minimum_centerline_distance_lower_bound_mm':worst,
            'minimum_tendon_surface_clearance_lower_bound_mm':worst-2*TENDON_RADIUS,
            'minimum_guide_envelope_clearance_lower_bound_mm':worst-2*GUIDE_OUTER_RADIUS,
            'worst_angle_deg':worstq,'length_variation_mm':max(lengths)-min(lengths),
            'max_tangent_or_position_join_error':max_error,
            'envelope':array_envelope(count,pitch=pitch),
            'clear_at_every_requested_sample':worst>2*GUIDE_OUTER_RADIUS and max_error<1e-9,
            'limitations':'Array envelopes only; excludes mount supports, bearings, outside leads, and whole-joint parts. Angular checks are requested samples, not a continuous-angle proof.'}


if __name__=='__main__':
    cases=[check_case(n,lim,STATION_PITCH) for n,lim in [(2,[-25,110]),(4,[-25,110]),(6,[-20,20]),(8,[-20,20]),(16,[-20,20])]]
    failed_pitch=check_case(2,[-25,110],2.2)
    output={'cases':cases,'requested_initial_pitch_audit':failed_pitch,
            'method':'Exact circular routes; nearest point sampling with along-curve Lipschitz error subtracted. Translation symmetry exhausts all channel pair offsets.'}
    destination=Path(__file__).with_name('axis_transport_report.json')
    destination.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
    if not all(c['clear_at_every_requested_sample'] for c in cases):
        raise SystemExit(1)
