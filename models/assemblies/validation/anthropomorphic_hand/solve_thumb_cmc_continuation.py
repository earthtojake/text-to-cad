import sys,json,time
import numpy as np
from scipy.spatial.transform import Rotation
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
ORDER=(-4.2,4.2,-5.4,5.4,-3.,3.)
source=json.loads(Path('models/assemblies/validation/anthropomorphic_hand/thumb_cmc_reorder_probe.json').read_text())
neutral=next(p for p in source if p['flex']==0 and p['yaw']==0)
cache=Path('models/assemblies/validation/anthropomorphic_hand/thumb_cmc_accepted_continuation.json')
out=json.loads(cache.read_text()) if cache.exists() else [neutral]
accepted={(p['flex'],p['yaw']):p for p in out}
# Keep the same branch by taking small increments from the nearest solved packet.
branches=[[(0.,float(y)) for y in range(-5,-26,-5)],[(0.,float(y)) for y in range(5,46,5)],[(float(f),0.) for f in range(-5,-16,-5)],[(float(f),0.) for f in range(5,66,5)],[(float(f),45.) for f in range(-5,-16,-5)],[(float(f),45.) for f in range(5,66,5)],[(float(f),-25.) for f in range(-5,-16,-5)],[(float(f),-25.) for f in range(5,66,5)]]
for branch in branches:
 for f,y in branch:
  if (f,y) in accepted:continue
  key=min(accepted,key=lambda p:(p[0]-f)**2+(p[1]-y)**2);prev={r['lane']:r for r in accepted[key]['rows']}
  oldR=Rotation.from_euler('z',key[1],degrees=True).as_matrix()@Rotation.from_euler('x',key[0],degrees=True).as_matrix()
  newR=Rotation.from_euler('z',y,degrees=True).as_matrix()@Rotation.from_euler('x',f,degrees=True).as_matrix()
  transport=Rotation.from_rotvec(Rotation.from_matrix(newR@oldR.T).as_rotvec()*.5).as_matrix()
  done=[];rows=[]
  for lane in ORDER:
   L=40 if abs(lane)==4.2 else 36;t=time.time()
   try:
    seed=np.array(prev[lane]['params']);
    for a in(2,5,8,11):seed[a:a+3]=transport@seed[a:a+3]
    cs,parameters=solve(f,y,lane,done,length=L,inlet_angle=35,initials_extra=([prev[lane]['params'],seed] if abs(lane)==3 else [seed,prev[lane]['params']]),only_extra=True);done.append(cs);rows.append({'lane':lane,'length':L,'params':parameters.tolist(),'curves':cs.tolist()});print('PASS',f,y,lane,round(time.time()-t,2),flush=True)
   except Exception as e:
    print('FAIL',f,y,lane,e,flush=True);Path('models/assemblies/validation/anthropomorphic_hand/thumb_cmc_continuation_failure.json').write_text(json.dumps({'flex':f,'yaw':y,'lane':lane,'error':str(e),'partial_rows':rows},indent=2));raise
  packet={'flex':f,'yaw':y,'inlet_angle':35,'rows':rows};accepted[(f,y)]=packet;out.append(packet)
  Path('models/assemblies/validation/anthropomorphic_hand/thumb_cmc_accepted_continuation.json').write_text(json.dumps(out,indent=2))
