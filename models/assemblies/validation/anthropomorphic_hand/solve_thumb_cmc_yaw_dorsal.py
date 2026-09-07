import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand')
old={(r['flex'],r['yaw']):r for r in json.loads((root/'thumb_cmc_accepted_continuation.json').read_text())}
start=next(p for p in json.loads((root/'thumb_cmc_dorsal_branch.json').read_text()) if p['flex']==0)
new={(0.,0.):start}
for sequence in [list(range(-5,-26,-5)),list(range(5,46,5))]:
 previous=start
 for yaw in sequence:
  t=time.time();R=Rotation.from_euler('z',(yaw-previous['yaw'])/2,degrees=True).as_matrix();prior={r['lane']:r for r in previous['rows']};same=old.get((0.,yaw));rows=[];others=[]
  for lane in(-4.2,4.2,-5.4,5.4,-3.,3.):
   L=40 if abs(lane)==4.2 else 36
   if same is not None and lane!=3.:
    source=next(r for r in same['rows'] if r['lane']==lane);seed=np.array(source['params'])
   else:
    seed=np.array(prior[lane]['params'])
    for i in(2,5,8,11):seed[i:i+3]=R@seed[i:i+3]
   cs,v=solve(0,yaw,lane,others,length=L,initials_extra=[seed,prior[lane]['params']],only_extra=True);others.append(cs);rows.append({'lane':lane,'length':L,'params':v.tolist(),'curves':cs.tolist()});print('PASS',yaw,lane,flush=True)
  previous={'flex':0.,'yaw':yaw,'rows':rows};new[(0.,yaw)]=previous;(root/'thumb_cmc_dorsal_yaw_branch.json').write_text(json.dumps(list(new.values()),indent=2));print('POSE',yaw,round(time.time()-t,2),flush=True)
