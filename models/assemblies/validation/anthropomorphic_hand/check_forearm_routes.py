"""Conservative complete-curve spacing checks for the actuator exit bundle."""
import sys,json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.layout import TENDONS
from lib.forearm_routing import forearm_route
from lib.path_analysis import path_length,path_min_radius,sample_path

rows=[]
for q in (-5*math.pi,0.,5*math.pi):
    routes=[forearm_route(t,q) for t in TENDONS]
    clouds=[sample_path(r['path'],.12) for r in routes]
    trees=[cKDTree(p) for p in clouds]
    minimum=(float('inf'),None,None)
    for i in range(len(routes)):
        for j in range(i+1,len(routes)):
            gap=float(trees[i].query(clouds[j])[0].min())-.12-.60
            if gap<minimum[0]:minimum=(gap,routes[i]['name'],routes[j]['name'])
    radius=float(min(path_min_radius(r['path']) for r in routes))
    rows.append({'rotation_rad':q,'minimum_bend_radius_mm':radius,
                 'certified_surface_gap_mm':minimum[0],'closest_pair':minimum[1:],
                 'clear':minimum[0]>0 and radius>=3.5,
                 'lengths_mm':{r['name']:path_length(r['path']) for r in routes}})
    print({k:v for k,v in rows[-1].items() if k!='lengths_mm'},flush=True)
dest=Path(__file__).with_name('forearm_path_precheck.json')
dest.write_text(json.dumps({'scope':'48 complete storage and forearm exit paths; curve-pair spacing and curvature only. Wrist and hardware clearance require separate gates.','samples':rows},indent=2))
assert all(r['clear'] for r in rows)
