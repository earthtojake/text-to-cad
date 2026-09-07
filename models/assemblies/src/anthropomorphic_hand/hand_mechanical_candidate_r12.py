"""Complete mechanical candidate assembled from the actual exported components.

The pose/explode gauntlet is still separate. Native reconstruction here keeps
this assembled export aligned with the components used by the physical audits.
"""
import hashlib,json
from pathlib import Path
from cadgen import step,read_step
from lib.native_integration import integrated_native_bodies,overlay,ROOT
from lib.assembly import compound

def native_parts(path):
    from cadgen.step_scene import load_step_scene,scene_occurrence_shape
    from build123d.importers import topods_lut
    from build123d.topology import downcast
    read_step(path)
    scene=load_step_scene(Path(path));stack=list(scene.roots);parts={}
    while stack:
        node=stack.pop();stack.extend(node.children)
        if node.prototype_key is None:continue
        name=str(node.name or node.source_name).strip();assert name not in parts
        raw=downcast(scene_occurrence_shape(scene,node));shape=topods_lut[type(raw)](raw)
        shape.label=name;parts[name]=shape
    return parts

@step(out='../../STEP/anthropomorphic_hand/hand_mechanical_candidate_r12.step')
def hand_mechanical_candidate_r12():
    bodies=integrated_native_bodies();folder=ROOT/'STEP/anthropomorphic_hand';reports=ROOT/'validation/anthropomorphic_hand'
    for family,filename in [('fingertip_pad','fingertip_pad_export_repair.step'),('fingernail','fingernail_export_repair_review.step')]:
        rows=json.loads((reports/f'{family}_export_repair_frames.json').read_text())
        bodies=overlay(bodies,folder/filename,rows,replace=True)
    repair=json.loads((reports/'static_clearance_relief_build.json').read_text());assert repair['pass']
    by_name={b.name:b for b in bodies}
    rows=[dict(name=n,frame=fr,system=by_name[n].system,kind=by_name[n].kind) for n,fr in repair['body_frames'].items()]
    bodies=overlay(bodies,folder/'static_clearance_relief_review.step',rows,replace=True)
    # Isolated R12 integration for final-export checking; whole-hand acceptance
    # remains separate until the complete static and aesthetic gates pass.
    for filename, gatefile in [
        ('fingertip_bridge_repair_review.step','fingertip_bridge_local_acceptance.json'),
        ('radial_bank_screw_clearance_candidate.step','radial_bank_screw_clearance_gate.json'),
        ('thumb_reaction_arm_clearance_r6.step','thumb_arm_r6_subset_gate.json')]:
        gate=json.loads((reports/gatefile).read_text());assert gate['pass']
        parts=native_parts(folder/filename);known={b.name:b for b in bodies}
        rows=[dict(name=name,frame=known[name].frame,system=known[name].system,kind=known[name].kind) for name in parts]
        bodies=overlay(bodies,folder/filename,rows,replace=True)
    inputs={b.source_path:b.source_sha256 for b in bodies}
    for path,digest in inputs.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
        selected=[b for b in bodies if b.source_path==path];native=native_parts(path)
        if len(native)==len(selected)==1:native={selected[0].name:next(iter(native.values()))}
        for body in selected:
            name=body.name;shape=native[name]
            shape.color=body.shape.color;shape.cad_material=dict(getattr(body.shape,'cad_material',{}));shape.label=name
            body.shape=shape
    assert len(bodies)==3257 and sum(b.frame!='variable' for b in bodies)==3039
    metadata=[dict(name=b.name,frame=b.frame,system=b.system,kind=b.kind) for b in bodies]
    (reports/'mechanical_candidate_r12_frames.json').write_text(json.dumps(metadata,indent=2)+'\n')
    evidence=dict(scope=__doc__,input_sha256=inputs,body_revisions={b.name:dict(step_sha256=b.source_sha256,frame=b.frame) for b in bodies})
    (reports/'mechanical_candidate_r12_build_inputs.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return compound(bodies,'mechanical_hand_candidate_r12')

if __name__=='__main__':hand_mechanical_candidate_r12()
