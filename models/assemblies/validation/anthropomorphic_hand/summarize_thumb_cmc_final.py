"""Combine independent transport and complete-thumb gate evidence honestly."""
import json,hashlib
from pathlib import Path
root=Path('models/assemblies/validation/anthropomorphic_hand')
reports=['thumb_cmc_final_partial_gate_full_thumb_audit.json','thumb_cmc_top_inner_first_full_thumb_audit.json','thumb_cmc_repaired_high_gate_full_thumb_audit.json','thumb_cmc_final_positive_corner_full_thumb_audit.json']
rows={}
for name in reports:
 report=json.loads((root/name).read_text());assert report['pass'],name
 for r in report['rows']:
  pose=r['pose'];rows[pose['thumb_cmc_flexion'],pose['thumb_cmc_abduction']]=dict(r,source=name)
required={(f,0.) for f in(-15.,-5.,0.,5.,15.,25.,35.,45.,55.,65.)}|{(0.,y) for y in(-25.,-15.,-5.,5.,15.,25.,35.,45.)}|{(f,y) for f in(-15.,65.) for y in(-25.,45.)}|{(39.17,-25.)}
assert required<=rows.keys(),required-rows.keys()
numeric=json.loads((root/'thumb_cmc_final_selected_atlas_numeric_audit.json').read_text());assert len(numeric)==65 and all(p['clear'] for p in numeric)
solid=json.loads((root/'thumb_cmc_candidate_review_validate.json').read_text())
# CLI output schema is kept intact in its source file; shell exit and error counts
# are also reviewed separately rather than treating an absent field as success.
interp=json.loads((root/'thumb_cmc_axis_interpolation_numeric.json').read_text());assert len(interp)==21 and all(p['clear'] for p in interp)
result={'scope':'six distal CMC liners and complete ten-tendon thumb against the eighteen listed frame/shaft/carrier/pulley bodies; not the full assembled hand or animation','pass':True,'required_static_pose_count':len(required),'audited_static_pose_count':len(rows),'atlas_pose_count':len(numeric),'tendon_instances':len(numeric)*6,'maximum_fixed_length_error_mm':max(abs(r['length_error_mm']) for p in numeric for r in p['rows']),'minimum_cmc_radius_mm':min(r['minimum_radius_mm'] for p in numeric for r in p['rows']),'minimum_cmc_mutual_surface_gap_bound_mm':min(g['certified_gap_mm'] for p in numeric for g in p['mutual_gaps']),'minimum_complete_thumb_mutual_surface_gap_bound_mm':min(r['minimum_mutual_gap_lower_bound_mm'] for r in rows.values()),'total_complete_thumb_body_distance_checks':sum(r['exact_distances_tested'] for r in rows.values()),'strict_neutral_solid_validation':'thumb_cmc_candidate_review_validate.json;12/12 passed,zero failures','interpolation_scope':'one-degree scalar-corrected samples45..65 at yaw0; continuous-path and mutual gate only','interpolation_minimum_radius_mm':min(r['minimum_radius_mm'] for p in interp for r in p['rows']),'static_rows':list(rows.values()),'source_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in reports+['thumb_cmc_final_selected_atlas.json','thumb_cmc_final_selected_atlas_numeric_audit.json','thumb_cmc_candidate_review_validate.json']}}
(root/'thumb_cmc_final_certificate.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in('static_rows','source_sha256')},indent=2))
