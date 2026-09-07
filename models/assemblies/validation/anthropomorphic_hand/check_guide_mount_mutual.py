"""Native every-body mutual check for guide assemblies with AABB broad phase."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import read_step
from check_guide_combs import common_volume
from check_middle_hardware_paths import bbox_gap

def leaves(n):return [a for c in n.children for a in leaves(c)] if n.children else [n]
def check(files):
 parts=[p for f in files for p in leaves(read_step(f))];bbs=[p.bounding_box(optimal=False) for p in parts]
 bad=[];count=0
 for i,p in enumerate(parts):
  for j in range(i):
   if bbox_gap(bbs[i],bbs[j])>1e-5:continue
   v=common_volume(p,parts[j]);count+=1
   if v>1e-7:bad.append({'a':p.label,'b':parts[j].label,'volume_mm3':v});print(bad[-1],flush=True)
 return {'pass':not bad,'bodies':len(parts),'exact_pairs':count,'interferences':bad}
if __name__=='__main__':
 name=sys.argv[1];files=[Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand'/f for f in sys.argv[2:]]
 r=check(files);Path(__file__).with_name(name+'_mutual.json').write_text(json.dumps(r,indent=2)+'\n');print(r,flush=True)
 if not r['pass']:raise SystemExit(1)
