"""Join original conservative sweep and the exact little-pad subset repair."""
import hashlib,json
from pathlib import Path
import numpy as np
from lib.layout import JOINTS,FINGERS

root=Path(__file__).parent
load=lambda name:json.loads((root/name).read_text())
baseline=load('fingertip_pad_report.json')
repair=load('fingertip_pad_little_repair.json')
strict=load('fingertip_pad_validate.json')
terminal=load('fingertip_pad_terminal_report.json')
contact=load('fingertip_pad_native_contact.json')
sources=Path('models/assemblies/src/anthropomorphic_hand/lib')
expected_body=3;expected_route=3
for j in JOINTS:
    lo,hi=j.limits;n=len(set([lo,hi,0.]+list(np.arange(lo,hi+1e-8,10.))))
    expected_body+=n
    if j.system in [f.name for f in FINGERS]+['thumb']:expected_route+=n
failures=[{'label':r['label'],**failure} for r in baseline['route_rows'] for failure in r['collisions']]
known=lambda r:r['label']=='full_fist_candidate' and r['group']=='little_mcp_flexion_positive_yaw_reaction' and r['body']=='little_fingertip_silicone_pad'
checks={
 'body_sweep_complete':len(baseline['body_rows'])==expected_body,
 'body_sweep_clear':all(r['pass'] for r in baseline['body_rows']),
 'route_sweep_complete':len(baseline['route_rows'])==expected_route and 'scope' in baseline,
 'all_reference_failures_resolved':all(known(r) for r in failures),
 'repair_and_mounts_pass':repair['pass'] and all(r['pass'] for r in baseline['mounts']),
 'strict_final_geometry_pass':strict.get('ok') is True and strict.get('occurrenceCount')==35 and strict.get('selfIntersectionCheck')=='every-placement',
 'terminal_orbits_and_cup_routes_pass':terminal['pass'],
 'pinch_has_contact_without_overlap':contact['exact_native_pad_gap_mm']<.001 and contact['intersection_mm3']<1e-7,
 'final_pad_source_matches_repair':hashlib.sha256((sources/'fingertip_pad.py').read_bytes()).hexdigest()==repair['source_sha256'],
 'host_sources_unchanged':all(hashlib.sha256((sources/n).read_bytes()).hexdigest()==h for n,h in baseline['source_sha256'].items() if n!='fingertip_pad.py'),
}
report={'pass':all(checks.values()),'checks':checks,'body_pose_count':len(baseline['body_rows']),'route_pose_count':len(baseline['route_rows']),'expected_route_pose_count':expected_route,'exact_body_pair_evaluations':sum(r['exact_pairs'] for r in baseline['body_rows']),'new_body_count':30,'strict_review_body_count':35,'pinch_contact':contact,'little_full_fist_liner_clearance_mm':repair['repaired_full_fist']['clearance_mm'],'minimum_continuous_terminal_clearance_mm':min(r['clearance_mm'] for r in terminal['terminal_orbits']),'reference_failures':failures,'scope':'The final little pad/carrier are exact geometric subsets of the conservative reference sweep; all other bodies are unchanged. Every clear reference pair is therefore still clear. The sole reference conflict is remeasured on final geometry. This certificate covers the specified sampled independent ranges, named poses, continuous terminal orbits, and cup route samples; it does not claim arbitrary simultaneous joint combinations or future assembly geometry.'}
(root/'fingertip_pad_acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not report['pass']:raise SystemExit(1)
