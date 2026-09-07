"""Recheck the complete repaired rigid core while final palm/housing additions build."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from check_full_route_bodies import integration_hardware
from check_assembly_interference import audit
from lib.palm_frame import make_palm_frame_bodies
root=Path(__file__).parent
bodies,evidence=integration_hardware()
exclude={p.label for p in make_palm_frame_bodies()}|{'fifth_metacarpal_cupping_truss'}
core=[b for b in bodies if b.name not in exclude]
print('CURRENT RIGID CORE',len(core),'deferredpalm',len(exclude),flush=True)
out=root/'repaired_core_interference.json';result=audit(core,out);result['deferred_palm_labels']=sorted(exclude);result['input_sha256']=evidence;result['scope']='Every current rigid body except the explicitly deferred main and cupping palm frames; not final assembly acceptance.';out.write_text(json.dumps(result,indent=2)+'\n')
if not result['pass']:raise SystemExit(1)
