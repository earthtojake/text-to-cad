"""Freeze native STEP occurrences needed for explicit local clearance repairs."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from cadgen.step_export import export_build123d_step_file
from check_native_reported_contacts import native_shapes

def main():
    report_path=HERE/'final_rigid_delta_gate.json';report=json.loads(report_path.read_text())
    contacts_path=HERE/'native_contact_regions.json';contacts=json.loads(contacts_path.read_text())
    names={row[key] for row in contacts['rows'] for key in ('a','b')}
    sources={h:Path(p) for p,h in report['input_sha256'].items() if p.endswith('.step')}
    records={n:report['body_revisions'][n] for n in names}
    shapes={};inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (report_path,contacts_path)}
    for digest in sorted({r['step_sha256'] for r in records.values()}):
        path=sources[digest];assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        inputs[str(path)]=digest;print('LOAD',path,flush=True)
        loaded=native_shapes(path)
        selected={n for n,r in records.items() if r['step_sha256']==digest}
        if len(loaded)==len(selected)==1:
            shapes[next(iter(selected))]=next(iter(loaded.values()))
        else:
            assert selected<=set(loaded)
            shapes.update({n:loaded[n] for n in selected})
    for name,s in shapes.items():s.label=name
    step=HERE.parents[1]/'STEP/anthropomorphic_hand/imported/rigid_clearance_inputs.step'
    export_build123d_step_file(bd.Compound(label='native_clearance_repair_inputs',children=[shapes[n] for n in sorted(shapes)]),step)
    manifest={'scope':__doc__,'input_sha256':inputs,'step':str(step),'step_sha256':hashlib.sha256(step.read_bytes()).hexdigest(),'bodies':records}
    (HERE/'rigid_clearance_inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('FROZEN',len(shapes),flush=True)

if __name__=='__main__':main()
