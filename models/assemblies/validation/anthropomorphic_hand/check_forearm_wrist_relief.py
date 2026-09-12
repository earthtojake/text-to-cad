"""Native frame/fork fit and material-subset certificate for local saddle relief."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.wrist import make_wrist_fixed_fork
root=Path(__file__).parent;step=root.parents[1]/'STEP/anthropomorphic_hand'
def leaves(s):return [x for c in s.children for x in leaves(c)] if s.children else [s]
newfile=step/'forearm_frame_review.step';oldfile=step/'hand_progress_review.step'
new=next(s for s in leaves(bd.import_step(str(newfile))) if s.label=='forearm_monolithic_24_seat_open_reaction_chassis')
old=next(s for s in leaves(bd.import_step(str(oldfile))) if s.label==new.label)
fork=make_wrist_fixed_fork();common=new&fork;added=new-old;removed=old-new
result={'frame_sha256':hashlib.sha256(newfile.read_bytes()).hexdigest(),'prior_assembly_sha256':hashlib.sha256(oldfile.read_bytes()).hexdigest(),'intersection_mm3':float(common.volume if common else 0),'new_material_outside_previous_frame_mm3':float(added.volume if added else 0),'removed_material_mm3':float(removed.volume if removed else 0),'native_frame_to_fork_distance_mm':float(new.distance_to(fork))}
result['pass']=result['intersection_mm3']<1e-8 and result['new_material_outside_previous_frame_mm3']<1e-8
(root/'forearm_wrist_relief_certificate.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)
if not result['pass']:raise SystemExit(1)
