"""Assemble and adaptively normalize the selected CMC control atlas."""
import sys,json,numpy as np
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import correct_length,curves_from_parameters
root=Path('models/assemblies/validation/anthropomorphic_hand');selected={}
for name in('thumb_cmc_final_axes_candidates.json','thumb_cmc_final_compounds_candidates.json','thumb_cmc_final_inner_first_axes.json','thumb_cmc_top_corners_candidates.json','thumb_cmc_top_positive_candidates.json'):
 for p in json.loads((root/name).read_text()):selected[p['flex'],p['yaw']]=p
for key in ((-15.,0.),(65.,0.),(0.,-25.),(0.,45.),(-15.,-25.),(-15.,45.),(65.,-25.),(65.,45.),(39.17,-25.)):
 assert key in selected,key
for p in selected.values():
 for r in p['rows']:
  assert len(r['params'])==(20 if abs(r['lane'])==3 else 14)
  v=correct_length(p['flex'],p['yaw'],r['lane'],r['params'],r['length'],outlet_y=16.);r['params']=v.tolist();r['curves']=curves_from_parameters(p['flex'],p['yaw'],r['lane'],v,outlet_y=16.).tolist()
 p['outlet_y']=16.
result=sorted(selected.values(),key=lambda p:(p['flex'],p['yaw']));path=root/'thumb_cmc_final_selected_atlas.json';path.write_text(json.dumps(result,indent=2)+'\n');print('selected',len(result),'packets;',len(result)*6,'curves')
