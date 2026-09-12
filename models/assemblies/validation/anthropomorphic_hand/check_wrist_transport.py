"""Routing-only development gate. Does not substitute for actual-solid tests."""
import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.layout import TENDONS
from lib.wrist_transport import plan_span
from lib.path_analysis import path_min_radius,path_length,sample_path

prior_path=Path(__file__).with_name('wrist_transport_neutral.json')
seeds={r['name']:r['parameters'] for r in json.loads(prior_path.read_text())['routes']} if prior_path.exists() else {}
routes=[];clouds=[];failures=[]
for t in TENDONS:
    try:
        r=plan_span(t,previous_cloud=np.concatenate(clouds) if clouds else None,seed=seeds.get(t['name']))
    except ValueError as e:
        failures.append(str(e));print('FAILED',e,flush=True);continue
    cloud=sample_path(r['path'],.025)
    gap=float('inf')
    if clouds:gap=float(cKDTree(np.concatenate(clouds)).query(cloud)[0].min())-.025-.9
    r.update({'minimum_bend_radius_mm':float(path_min_radius(r['path'])),
              'length_mm':float(path_length(r['path'])),'certified_prior_surface_gap_mm':gap})
    routes.append(r);clouds.append(cloud)
    print(r['name'],'radius',round(r['minimum_bend_radius_mm'],5),'gap',round(gap,5),flush=True)
dest=Path(__file__).with_name('wrist_transport_neutral.json')
dest.write_text(json.dumps({'scope':'48 neutral guide curve spacing and radius only; actual frame/wrist geometry not yet checked','routes':routes,'failures':failures},indent=2))
assert not failures and len(routes)==48
assert all(r['minimum_bend_radius_mm']>=3.5 and r['certified_prior_surface_gap_mm']>0 for r in routes)
