"""Repair the foreign index span against the unchanged CMC axis envelope."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from lib.wrist_transport import plan_span
from lib.layout import TENDONS
from lib.path_analysis import sample_path,path_min_radius,path_length
from lib.transport_guide import path_wire
from lib.universal_carrier import make_universal_carrier
from lib.joint_hardware import joint_hardware
from lib.layout import THUMB_CMC
from cadgen import build123d as bd
root=Path(__file__).parent;source=json.loads((root/'wrist_transport_neutral.json').read_text());name='index_mcp_abduction_positive';tendon=next(t for t in TENDONS if t['name']==name)
old=next(r for r in source['routes'] if r['name']==name);cloud=np.concatenate([sample_path(r['path'],.025) for r in source['routes'] if r['name']!=name])
print('solving foreignCMC clearance',flush=True);r=plan_span(tendon,{},previous_cloud=cloud,seed=old['parameters'])
gap=float(cKDTree(cloud).query(sample_path(r['path'],.025))[0].min())-.925
carrier=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*make_universal_carrier(phalanx_width=19.,yaw_plane=9.5,label='thumb_cmc_carrier')
parts=[carrier]+[s for s,f,sy,k in joint_hardware() if s.label=='thumb_cmc_flexion_positive_bushing']
w=path_wire(r['path']);distances={s.label:w.distance_to(s)-.45 for s in parts}
report={'route':r,'minimum_radius_mm':path_min_radius(r['path']),'mutual_surface_gap_lower_bound_mm':gap,'actual_body_surface_clearances_mm':distances,'length_mm':path_length(r['path']),'pass':gap>0 and path_min_radius(r['path'])>=3.5 and all(d>0 for d in distances.values())}
(root/'index_wrist_foreign_cmc_candidate.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='route'},flush=True)
if not report['pass']:raise SystemExit(1)
