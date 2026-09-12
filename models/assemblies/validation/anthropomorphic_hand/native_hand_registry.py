"""Reconstruct the integration's actual STEP shapes, preserving their frames."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.assembly import Body
from check_native_reported_contacts import native_shapes

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def native_current_bodies(include_reliefs=False):
    old_path=HERE/'final_rigid_delta_gate.json';old=json.loads(old_path.read_text())
    metadata_path=HERE/'hand_native_body_frames.json'
    metadata={r['name']:r for r in json.loads(metadata_path.read_text())}
    revisions={n:dict(r) for n,r in old['body_revisions'].items()}
    sources={h:Path(p) for p,h in old['input_sha256'].items() if p.endswith('.step')}
    inputs={str(p):sha(p) for p in (old_path,metadata_path,Path(__file__),HERE/'check_native_reported_contacts.py')}
    pad_gate_path=HERE/'fingertip_pad_export_roundtrip.json';pad_gate=json.loads(pad_gate_path.read_text());assert pad_gate['pass']
    pad=HERE.parents[1]/'STEP/anthropomorphic_hand/fingertip_pad_export_repair.step'
    pad_hash=sha(pad);assert pad_gate['input_sha256'][str(pad)]==pad_hash
    inputs[str(pad_gate_path)]=sha(pad_gate_path);sources[pad_hash]=pad
    pad_frames_path=HERE/'fingertip_pad_export_repair_frames.json'
    inputs[str(pad_frames_path)]=sha(pad_frames_path)
    for row in json.loads(pad_frames_path.read_text()):
        assert row['name'] in revisions
        revisions[row['name']]={'step_sha256':pad_hash,'frame':row['frame']};metadata[row['name']]=row
    nail_gate_path=HERE/'fingernail_export_roundtrip.json';nail_gate=json.loads(nail_gate_path.read_text());assert nail_gate['pass']
    nail=pad.parent/'fingernail_export_repair_review.step'
    nail_hash=sha(nail);assert nail_gate['input_sha256'][str(nail)]==nail_hash
    inputs[str(nail_gate_path)]=sha(nail_gate_path);sources[nail_hash]=nail
    nail_frames_path=HERE/'fingernail_export_repair_frames.json'
    inputs[str(nail_frames_path)]=sha(nail_frames_path)
    for row in json.loads(nail_frames_path.read_text()):
        assert row['name'] in revisions and row['frame']==revisions[row['name']]['frame']
        revisions[row['name']]={'step_sha256':nail_hash,'frame':row['frame']};metadata[row['name']]=row
    if include_reliefs:
        proof_path=HERE/'static_clearance_relief_build.json';proof=json.loads(proof_path.read_text());assert proof['pass']
        step=pad.parent/'static_clearance_relief_review.step';digest=sha(step);sources[digest]=step;inputs[str(proof_path)]=sha(proof_path)
        for name,frame in proof['body_frames'].items():
            assert name in revisions and revisions[name]['frame']==frame
            revisions[name]={'step_sha256':digest,'frame':frame}
    bodies=[]
    for digest in sorted({r['step_sha256'] for r in revisions.values()}):
        path=sources[digest];assert sha(path)==digest;inputs[str(path)]=digest
        print('NATIVE INPUT',path,flush=True);shapes=native_shapes(path)
        selected={n for n,r in revisions.items() if r['step_sha256']==digest}
        if len(shapes)==len(selected)==1:shapes={next(iter(selected)):next(iter(shapes.values()))}
        assert selected<=set(shapes)
        for name in sorted(selected):
            row=metadata[name];assert row['frame']==revisions[name]['frame']
            shape=shapes[name];shape.label=name
            body=Body(shape,row['frame'],row['system'],row['kind'])
            body.source_sha256=digest;body.source_path=str(path);bodies.append(body)
    assert len(bodies)==len(revisions)==3039
    return sorted(bodies,key=lambda b:b.name),inputs
