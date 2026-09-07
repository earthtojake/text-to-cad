import sys,json,numpy as np
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import correct_length,curves_from_parameters
from check_thumb_cmc_transport import numeric
root=Path('models/assemblies/validation/anthropomorphic_hand');data=json.loads((root/'thumb_cmc_final_axes_candidates.json').read_text());high=json.loads((root/'thumb_cmc_final_inner_first_axes.json').read_text());d={(p['flex'],p['yaw']):p for p in data};d.update({(p['flex'],p['yaw']):p for p in high});out=[]
for f in np.arange(45,65.001,1.):
 low=max(p for p,y in d if y==0 and p<=f);upper=min(p for p,y in d if y==0 and p>=f);a=d[low,0];b=d[upper,0];t=0 if upper==low else (f-low)/(upper-low);rows=[]
 for r in a['rows']:
  s=next(s for s in b['rows'] if s['lane']==r['lane']);v=(1-t)*np.array(r['params'])+t*np.array(s['params']);v=correct_length(f,0,r['lane'],v,r['length'],outlet_y=16);cs=curves_from_parameters(f,0,r['lane'],v,outlet_y=16);rows.append({'lane':r['lane'],'length':r['length'],'params':v.tolist(),'curves':cs.tolist()})
 report=numeric(rows,f,0);report.update(flex=float(f),yaw=0.);out.append(report);print(f,report['clear'],min(r['minimum_radius_mm'] for r in report['rows']),min(g['certified_gap_mm'] for g in report['mutual_gaps']),flush=True);(root/'thumb_cmc_axis_interpolation_numeric.json').write_text(json.dumps(out,indent=2))
