"""Native six-turn envelope proof for each spool and captured rope termination.

Each operational stored rope is a prefix of the same six-turn swept tube after
undoing its spool rotation. A zero intersection for that containing tube proves
every such prefix clear of the co-rotating capstan, ferrule and bond line.
The changing external lead and other hardware remain separate checks.
"""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;LIB=HERE.parents[1]/'src/anthropomorphic_hand/lib'
sys.path.insert(0,str(LIB.parent))
from cadgen import build123d as bd
from check_native_reported_contacts import native_shapes
from lib.layout import TENDONS
from lib.assembly import matrix_location
from lib.capstan_path import full_groove_path
from lib.transport_guide import make_tendon
from lib.phalanx_r5_boolean import common
KINDS=('capstan','terminal_ferrule','capstan_terminal_bond_line')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    registry_path=HERE/'final_rigid_delta_gate.json';registry=json.loads(registry_path.read_text())
    sources={h:Path(p) for p,h in registry['input_sha256'].items() if p.endswith('.step')}
    inputs={str(p):sha(p) for p in (Path(__file__),registry_path,HERE/'check_native_reported_contacts.py',*[LIB/n for n in ('layout.py','assembly.py','capstan_path.py','transport_guide.py','phalanx_r5_boolean.py')])}
    native={};prototypes={};rows=[];revisions={}
    for tendon in TENDONS:
        placement=np.eye(4);placement[:3,:3]=np.diag([tendon['sign'],1.,tendon['sign']]);placement[:3,3]=tendon['capstan_center']
        for kind in KINDS:
            name=tendon['actuator']+'_'+kind;revision=registry['body_revisions'][name];digest=revision['step_sha256'];path=sources[digest]
            assert sha(path)==digest;inputs[str(path)]=digest;revisions[name]=revision
            if digest not in native:native[digest]=native_shapes(path)
            shape=native[digest][name];assert len(shape.solids())==1
            restored=bd.Compound.cast(shape.wrapped.Moved(matrix_location(np.linalg.inv(placement)).wrapped)).solids()[0]
            reference=prototypes.setdefault(kind,restored)
            partner=restored.wrapped.IsPartner(reference.wrapped)
            def matrix(s):
                t=s.wrapped.Location().Transformation();return np.array([[t.Value(i,j) for j in range(1,5)] for i in range(1,4)])
            error=float(np.max(np.abs(matrix(restored)-matrix(reference))))
            assert partner and error<1e-10,(name,partner,error)
            rows.append(dict(body=name,kind=kind,identical_native_topology=partner,maximum_canonical_placement_error=error))
    tube=make_tendon(full_groove_path(),'six_turn_storage_envelope');assert len(tube.solids())==1 and tube.is_valid
    checks=[]
    for kind,shape in prototypes.items():
        volume=sum(s.volume for s in common(tube,shape).solids());print('NATIVE STORAGE ENVELOPE',kind,volume,flush=True)
        checks.append(dict(kind=kind,intersection_mm3=volume,pass_=volume<=1e-8))
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,body_revisions=revisions,occurrences=rows,envelope_checks=checks,canonical_path=full_groove_path(),rope_radius_mm=.30,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in checks));report['pass']=report.pop('pass_')
    (HERE/'native_capstan_envelope_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
