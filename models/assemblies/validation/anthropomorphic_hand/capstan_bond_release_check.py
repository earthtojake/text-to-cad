"""Two-leg resin-sleeve release after capstan tendon and ferrule removal."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.drive_terminal import make_capstan_bond_line
root=read_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/capstan_review.step')
def leaves(node):
 return [s for c in node.children for s in leaves(c)] if node.children else [node]
parts=leaves(root)
capstan=next(p for p in parts if p.label=='six_turn_storage_capstan')
bond=make_capstan_bond_line();checks=[]
for z in [*([i*.025 for i in range(1,15)]),.37]:
 s=bd.Pos(0,0,z)*bond;checks.append({'stage':'axial','x':0.,'z':z,'overlap':(s&capstan).volume})
for i in range(1,11):
 x=i*.05;s=bd.Pos(x,0,.37)*bond;checks.append({'stage':'radial','x':x,'z':.37,'overlap':(s&capstan).volume})
r={'ok':all(c['overlap']<1e-7 for c in checks),'steps':checks,
   'precondition':'rope tip advanced0.85mm and steel ferrule removed',
   'local_stages':[{'delta':[0.,0.,.37]},{'delta':[.50,0.,0.]}]}
Path(__file__).with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r),flush=True)
assert r['ok']
