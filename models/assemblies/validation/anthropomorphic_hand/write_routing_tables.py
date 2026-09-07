"""Publish exact neutral path facts and explicitly scoped drive/motion evidence."""
import hashlib,json
from pathlib import Path
import numpy as np
from lib.layout import TENDONS,JOINTS,MINIMUM_BEND_RADIUS
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.path_analysis import path_length,path_min_radius
from lib.finger_routing import endpoint,tangent
ROOT=Path(__file__).parent
rows=[]
for tendon,route in zip(TENDONS,NEUTRAL_ROUTES):
    path=route['path'];gaps=[np.linalg.norm(np.array(endpoint(a,True))-endpoint(b)) for a,b in zip(path,path[1:])]
    tangent_errors=[np.linalg.norm(np.array(tangent(a,True))-tangent(b)) for a,b in zip(path,path[1:])]
    rows.append({'tendon':tendon['name'],'length_mm':path_length(path),'joints_crossed':[*tendon['upstream'],tendon['joint']], 'minimum_bend_radius_mm':path_min_radius(path),'required_minimum_bend_radius_mm':MINIMUM_BEND_RADIUS,'maximum_join_gap_mm':float(max(gaps,default=0.)),'maximum_tangent_error':float(max(tangent_errors,default=0.)),'geometry_clearance':'PENDING COMPLETE ASSEMBLY GATE'})
assert len(rows)==48
p=Path('models/assemblies/src/anthropomorphic_hand/lib/neutral_routes.py')
report={'routing_scheme':'48 independently actuated antagonistic tendons for24DOF','tendon_count':48,'actuator_count':48,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':rows}
(ROOT/'neutral_path_table.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['# Routing and motion evidence','', '48 antagonistic tendons,48 independent motor/gearbox/capstan actuators;24DOF including palm cupping and two wrist axes. Rope radius0.30mm; minimum bend radius3.50mm.','', '**Assembly clearance remains pending. These path facts do not replace the complete solid, motion, and animated-frame gates.**','','| Tendon | Length mm | Joints crossed | Minimum radius mm | Clear |','|---|---:|---|---:|---|']
for r in rows:lines.append(f"| {r['tendon']} | {r['length_mm']:.3f} | {', '.join(r['joints_crossed'])} | {r['minimum_bend_radius_mm']:.6f} | Pending |")
moment_path=ROOT/'all_joint_moment_arms.json'
moment=json.loads(moment_path.read_text()) if moment_path.exists() else {}
moment_pass=moment.get('pass') and len(moment.get('joints',[]))==24
lines+=['','## Joint drive signs','','Each named target has a positive and negative driven wrap. Upstream constant-working-length reaction liners cancel the net upstream cable actuation; wrist span changes require explicit capstan compensation. Numerical virtual-work checks evaluate every tendon against every axis; wrist transport compensation is separate.','','| Joint | Positive drive / moment mm | Negative drive / moment mm | Other crossing tendons | Certification |','|---|---|---|---|---|']
for joint in JOINTS:
    crossed=[t['name'] for t in TENDONS if joint.name in t['upstream']]
    lines.append(f"| {joint.name} | {joint.name}_positive / +{joint.drive_radius:g} | {joint.name}_negative / −{joint.drive_radius:g} | {', '.join(crossed) or 'None'} | {'48-tendon finite-difference check passed' if moment_pass else 'Pending'} |")
global_path=ROOT/'global_phalanx_sweeps.json'
if global_path.exists():
    evidence=json.loads(global_path.read_text());lines+=['','## Phalange collision samples','','Exact STEP-solid pair intersections for15 phalanges. Hardware and tendons are separate gates.','','| Sample | Exact pairs | Reused exact relative-state certificates | Clear |','|---|---:|---:|---|']
    for r in evidence['rows']:lines.append(f"| {r['sample']} | {r['exact_pairs']} | {r['unchanged_relative_pair_certificates_reused']} | {'Yes' if r['clear'] else 'NO'} |")
(ROOT/'ROUTING_AND_COLLISION_TABLES.md').write_text('\n'.join(lines)+'\n')
print({'tendons':len(rows),'total_length_mm':sum(r['length_mm'] for r in rows),'min_radius_mm':min(r['minimum_bend_radius_mm'] for r in rows),'max_join_gap_mm':max(r['maximum_join_gap_mm'] for r in rows),'max_tangent_error':max(r['maximum_tangent_error'] for r in rows)})
