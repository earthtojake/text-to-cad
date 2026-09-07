"""Compose scoped mount certificates after a one-body structural revision.

Original failed reports remain immutable evidence. Only checks involving the
explicitly revised body are replaced by its full actual-geometry recheck.
"""
from pathlib import Path
import hashlib,json
base=Path(__file__).parent
changed='thumb_cmc_child_four_liner_comb_structural_jaw'
def read(name):return json.loads((base/name).read_text())
def combined_body(label,oldname,newname):
 old=read(oldname);new=read(newname)
 assert len(old['rows'])==len(new['rows'])==1 and new['pass']
 row=old['rows'][0]
 remaining=[c for c in row['solid_conflicts'] if changed not in (c.get('mount'),c.get('other_mount'))]
 assert not remaining and not row['route_conflicts']
 return {'pose':label,'pass':True,'original_report':oldname,'changed_body_report':newname,'method':'23 unchanged bodies retain checks; revised structural jaw rechecked versus every other mount, thumb hardware, and routes','palm_host_certificate':'pending rebuild'}
rows=[combined_body('neutral','thumb_cmc_mounts_thumb_bodies_report.json','thumb_cmc_changed_strut_body_report.json'),combined_body('final precision pinch','thumb_cmc_mounts_pinch_thumb_bodies_report.json','thumb_cmc_changed_strut_pinch_report.json')]
a=read('thumb_cmc_mounts_routes_report.json');b=read('thumb_cmc_changed_strut_routes_report.json')
assert a['pass'] and b['pass'] and len(a['rows'])==len(b['rows'])==25
assert [r['pose'] for r in a['rows']]==[r['pose'] for r in b['rows']]
strict=read('thumb_cmc_mounts_validate.json');assert strict['ok'] and strict['occurrenceCount']==24
step=Path('models/assemblies/STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step')
report={'scoped_pass':True,'body_count':24,'step_sha256':hashlib.sha256(step.read_bytes()).hexdigest(),'strict_every_placement_pass':True,'actual_body_rows':rows,'tendon_mount_gate':{'pass':True,'poses':25,'all_mounts_original_distance_checks':sum(r['route_distance_checks'] for r in a['rows']),'revised_body_distance_checks':sum(r['route_distance_checks'] for r in b['rows']),'reports':['thumb_cmc_mounts_routes_report.json','thumb_cmc_changed_strut_routes_report.json']},'parent_attachment':{'frame':'CMC parent','point':[2.98,-8,-17.98],'axis':[0,0,1],'footprint_mm':[4,1]},'palm_host_certificate':'pending palm rebuild','articulated_mount_body_sweep_certificate':'pending final assembly','animation_certificate':False,'full_assembly_certificate':False}
(base/'thumb_cmc_mounts_release_status.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
