import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand')
old=next(p for p in json.loads((root/'thumb_cmc_outlet16_axes.json').read_text()) if p['flex']==0 and p['yaw']==0)
base=np.array(next(r for r in old['rows'] if r['lane']==-3)['params']);others=[];rows=[]
for lane in(-4.2,4.2,-5.4,5.4,-3.,3.):
 if abs(lane)==4.2:seed=np.array(next(r for r in old['rows'] if r['lane']==lane)['params'])
 else:
  seed=base.copy()
  for i in(2,8):seed[i]+=lane+3
 L=40 if abs(lane)==4.2 else 36
 cs,v=solve(0,0,lane,others,length=L,initials_extra=[seed],only_extra=True,outlet_y=16);others.append(cs);rows.append({'lane':lane,'length':L,'params':v.tolist(),'curves':cs.tolist()});print('NEUTRAL',lane,flush=True)
previous={'flex':0.,'yaw':0.,'outlet_y':16,'rows':rows};out=[previous];(root/'thumb_cmc_dorsal_bank.json').write_text(json.dumps(out,indent=2))
for f in range(5,66,5):
 R=Rotation.from_euler('x',2.5,degrees=True).as_matrix();rows=[];others=[];t=time.time()
 for row in previous['rows']:
  seed=np.array(row['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  cs,v=solve(f,0,row['lane'],others,length=row['length'],initials_extra=[seed,row['params']],only_extra=True,outlet_y=16);others.append(cs);rows.append({'lane':row['lane'],'length':row['length'],'params':v.tolist(),'curves':cs.tolist()});print('PASS',f,row['lane'],flush=True)
 previous={'flex':f,'yaw':0.,'outlet_y':16,'rows':rows};out.append(previous);(root/'thumb_cmc_dorsal_bank.json').write_text(json.dumps(out,indent=2));print('POSE',f,round(time.time()-t,2),flush=True)
