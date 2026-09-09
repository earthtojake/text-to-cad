"""New fist and corrected pad/nail pairs against every native rigid body.

Unchanged-frame, unchanged-shape pairs remain the separate static baseline's
responsibility. This is a pose delta, not a complete assembly certificate.
"""
import gzip,hashlib,json
from pathlib import Path
from native_hand_registry import native_current_bodies,sha,HERE
from check_native_assembly_interference import audit
from lib.assembly import posed_bodies

def main():
    bodies,inputs=native_current_bodies()
    candidate_path=HERE/'final_fist_candidate.json';candidate=json.loads(candidate_path.read_text());inputs[str(candidate_path)]=sha(candidate_path)
    for p in (Path(__file__),HERE/'check_native_assembly_interference.py',HERE/'rigid_separation_filter.py',HERE/'rigid_pose_cache.py'):inputs[str(p)]=sha(p)
    changed={b.name for b in bodies if (b.frame.startswith(('index_','middle_','ring_','little_')) and b.frame.endswith(('_mcp_flexion','_pip','_dip'))) or b.frame.startswith('thumb_') or '_fingertip_' in b.name or 'fingernail' in b.name}
    cache={};checkpoint=HERE/'final_fist_rigid_checkpoint.json.gz'
    def tuples(value):return tuple(tuples(v) for v in value) if isinstance(value,list) else value
    if checkpoint.exists():
        saved=json.loads(gzip.decompress(checkpoint.read_bytes()))
        if saved['input_sha256']==inputs:cache={tuples(k):v for k,v in saved['cache']}
    def save(cache):
        temporary=checkpoint.with_suffix('.tmp');temporary.write_bytes(gzip.compress(json.dumps({'input_sha256':inputs,'cache':list(cache.items())},separators=(',',':')).encode()));temporary.replace(checkpoint)
    out=HERE/'final_fist_rigid_delta.json'
    report=audit(posed_bodies(bodies,candidate['pose']),out,cache=cache,changed_names=changed,pose=candidate['pose'],on_progress=save)
    report.update(scope=__doc__,input_sha256=inputs,pose=candidate['pose'],sample=candidate['label'])
    report['changed_during_audit']=[p for p,h in inputs.items() if sha(p)!=h]
    report['pass'] &= not report['changed_during_audit'];out.write_text(json.dumps(report,indent=2)+'\n')
    assert report['pass']

if __name__=='__main__':main()
