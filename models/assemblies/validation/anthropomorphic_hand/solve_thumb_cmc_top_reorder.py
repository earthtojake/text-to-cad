import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand');previous=json.loads((root/'thumb_cmc_dorsal_bank_fourspan.json').read_text())[-1];out=[]
for f in(65.,):
 R=Rotation.from_euler('x',(f-previous['flex'])/2,degrees=True).as_matrix();rows=[];others=[]
 for lane in(-4.2,4.2,-3.,3.,-5.4,5.4):
  row=next(r for r in previous['rows'] if r['lane']==lane);seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  seeds=[seed,row['params']]
  if lane==-3:seeds.insert(0,json.loads((root/'thumb_cmc_inner65_unrestricted.json').read_text())['params'])
  t=time.time();cs,v=solve(f,0,lane,others,length=row['length'],initials_extra=seeds,only_extra=True,outlet_y=16,span_count=4 if abs(lane)==3 else 3,diagnostic=lambda x:print('ATTEMPT',lane,{k:v for k,v in x.items() if k!='parameters'},flush=True));others.append(cs);rows.append({'lane':lane,'length':row['length'],'params':v.tolist(),'curves':cs.tolist()});print('PASS',f,lane,round(time.time()-t,2),flush=True)
 previous={'flex':f,'yaw':0.,'outlet_y':16,'rows':rows};out.append(previous);(root/'thumb_cmc_top_reorder.json').write_text(json.dumps(out,indent=2))
