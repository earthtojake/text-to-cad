import sys,json,time,numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand')
start=json.loads((root/'thumb_cmc_outlet16_topflex.json').read_text())[0]
cache=root/'thumb_cmc_outlet16_axes.json'
out=json.loads(cache.read_text()) if cache.exists() else [start]
old_atlas=json.loads((root/'thumb_cmc_dorsal_branch.json').read_text())+json.loads((root/'thumb_cmc_dorsal_yaw_branch.json').read_text())
def packet(previous,f,y):
 existing=next((r for r in out if r['flex']==f and r['yaw']==y),None)
 if existing:return existing
 matching=next((r for r in old_atlas if r['flex']==f and r['yaw']==y),None)
 oldR=Rotation.from_euler('z',previous['yaw'],degrees=True).as_matrix()@Rotation.from_euler('x',previous['flex'],degrees=True).as_matrix()
 newR=Rotation.from_euler('z',y,degrees=True).as_matrix()@Rotation.from_euler('x',f,degrees=True).as_matrix()
 R=Rotation.from_rotvec(Rotation.from_matrix(newR@oldR.T).as_rotvec()*.5).as_matrix();rows=[];others=[]
 for old in previous['rows']:
  seed=np.array(old['params'])
  for i in range(2,len(seed),3):seed[i:i+3]=R@seed[i:i+3]
  seeds=[seed,old['params']]
  if matching:seeds.insert(0,next(r['params'] for r in matching['rows'] if r['lane']==old['lane']))
  cs,v=solve(f,y,old['lane'],others,length=old['length'],initials_extra=seeds,outlet_y=16);others.append(cs);rows.append({'lane':old['lane'],'length':old['length'],'params':v.tolist(),'curves':cs.tolist()})
  print('PASS',f,y,old['lane'],flush=True)
 result={'flex':f,'yaw':y,'outlet_y':16,'rows':rows};out.append(result);(root/'thumb_cmc_outlet16_axes.json').write_text(json.dumps(out,indent=2));return result
previous=start
for f in range(45,-16,-5):previous=packet(previous,float(f),0.)
neutral=next(r for r in out if r['flex']==0 and r['yaw']==0)
for ys in (range(-5,-26,-5),range(5,46,5)):
 previous=neutral
 for y in ys:previous=packet(previous,0.,float(y))
