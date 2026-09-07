import sys,json,numpy as np
from pathlib import Path
from scipy.spatial import cKDTree
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import solve
from lib.bowden_mcp import sampled_points
root=Path('models/assemblies/validation/anthropomorphic_hand');p=json.loads((root/'thumb_cmc_dorsal_bank_fourspan.json').read_text())[-1];inner=json.loads((root/'thumb_cmc_inner65_unrestricted.json').read_text());cloud=sampled_points(np.asarray(inner['curves']),501)
for r in p['rows'][:2]:
 cs,v=solve(65,0,r['lane'],[],length=40,initials_extra=[r['params']],only_extra=True,outlet_y=16);other=sampled_points(cs,501);d,i=cKDTree(cloud).query(other);j=d.argmin();print(r['lane'],d[j],cloud[i[j]],other[j],flush=True)
