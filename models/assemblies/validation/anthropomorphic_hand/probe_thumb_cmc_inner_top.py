import sys,json,numpy as np
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
root=Path('models/assemblies/validation/anthropomorphic_hand');p=json.loads((root/'thumb_cmc_dorsal_bank_top_fine.json').read_text())[-1];r=next(r for r in p['rows'] if r['lane']==-3.)
log=[]
def report(x):
 log.append(x);(root/'thumb_cmc_inner_top_diagnostic.json').write_text(json.dumps(log,indent=2));print({k:v for k,v in x.items() if k!='parameters'},flush=True)
cs,v=solve(65,0,-3.,[],length=36.,initials_extra=[r['params']],only_extra=True,outlet_y=16,span_count=4,diagnostic=report)
print('PASS unrestricted neighbors',flush=True);(root/'thumb_cmc_inner65_unrestricted.json').write_text(json.dumps({'lane':-3,'params':v.tolist(),'curves':cs.tolist()},indent=2))
