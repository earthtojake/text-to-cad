"""Full-range wrist curve gate; hardware and cup spans are separate gates."""
import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.layout import TENDONS,JOINT_BY_NAME
from lib.wrist_transport import plan_span
from lib.path_analysis import path_min_radius,path_length,sample_path

root=Path(__file__).parent
neutral=json.loads((root/'wrist_transport_neutral.json').read_text())
seeds={r['name']:r['parameters'] for r in neutral['routes']}
samples=[]
for joint in ('wrist_flexion','wrist_abduction'):
    lo,hi=JOINT_BY_NAME[joint].limits
    samples += [(joint,float(q)) for q in sorted(set(np.arange(lo,hi+1e-8,10).tolist()+[hi]),key=abs)]
results=[]
branches={}
for joint,q in samples:
    clouds=[];routes=[];failures=[];pose={joint:q}
    branch=branches.setdefault((joint,1 if q>=0 else -1),dict(seeds))
    for t in TENDONS:
        try:r=plan_span(t,pose,previous_cloud=np.concatenate(clouds) if clouds else None,seed=branch[t['name']])
        except ValueError as e:failures.append(str(e));print('FAILED',pose,e,flush=True);continue
        cloud=sample_path(r['path'],.025);gap=float('inf')
        if clouds:gap=float(cKDTree(np.concatenate(clouds)).query(cloud)[0].min())-.925
        r.update(minimum_bend_radius_mm=float(path_min_radius(r['path'])),
                 length_mm=float(path_length(r['path'])),certified_prior_surface_gap_mm=gap)
        routes.append(r);clouds.append(cloud)
        branch[t['name']]=r['parameters']
    clear=(not failures and len(routes)==48 and all(r['minimum_bend_radius_mm']>=3.5 and r['certified_prior_surface_gap_mm']>0 for r in routes))
    results.append({'pose':pose,'clear':clear,'routes':routes,'failures':failures})
    (root/'wrist_motion_routes.json').write_text(json.dumps({'scope':'48 wrist crossing curve radius and spacing; hardware and cup reaction interfaces pending','samples':results},indent=2))
    print('POSE',pose,'routes',len(routes),'clear',clear,'min_radius',min(r['minimum_bend_radius_mm'] for r in routes),'min_gap',min(r['certified_prior_surface_gap_mm'] for r in routes),flush=True)
assert all(r['clear'] for r in results)
