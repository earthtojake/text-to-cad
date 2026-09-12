"""Native material equivalence between audited components and the R13 export.

STEP re-export can rebuild pcurves, so BREP bytes need not be identical. Both
directed native differences must have no faces to establish material equality.
This gate complements direct strict validation of the assembled export.
"""
import argparse
import hashlib
import json
import multiprocessing
from pathlib import Path
import numpy as np

from check_native_reported_contacts import HERE, native_shapes
from lib.phalanx_r5_boolean import cut
from cadgen._internal.component_package import _shape_brep_bytes

JOBS=[]
MEMBERS=[]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(index):
    name,source,exported=JOBS[index]
    assert len(source.solids())==len(exported.solids())==1,name
    added=cut(exported,source)
    removed=cut(source,exported)
    row=dict(body=name,added_faces=len(added.faces()),removed_faces=len(removed.faces()),
             added_solids=len(added.solids()),removed_solids=len(removed.solids()),
             added_volume_mm3=sum(s.volume for s in added.solids()),
             removed_volume_mm3=sum(s.volume for s in removed.solids()),
             pass_=not added.faces() and not removed.faces())
    print('EXPORT MATERIAL',name,row,flush=True)
    return row


def placement(shape):
    t=shape.wrapped.Location().Transformation()
    return np.asarray([[t.Value(r,c) for c in range(1,5)] for r in range(1,4)])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sample',action='append')
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand'
    document=folder/'hand_mechanical_candidate_r13.step'
    buildpath=HERE/'mechanical_candidate_r13_build_inputs.json'
    build=json.loads(buildpath.read_text())
    inputs={str(p):sha(p) for p in (Path(__file__),document,buildpath,HERE/'check_native_reported_contacts.py',
                                    HERE.parents[1]/'src/anthropomorphic_hand/lib/phalanx_r5_boolean.py')}
    assert all(sha(p)==h for p,h in build['input_sha256'].items())
    inputs.update(build['input_sha256'])
    native=native_shapes(document)
    assert len(native)==3259 and set(native)==set(build['body_revisions'])
    names=set(args.sample) if args.sample else set(native)
    assert names and names<=set(native)
    sources={digest:Path(path) for path,digest in build['input_sha256'].items()}
    for digest in sorted({build['body_revisions'][n]['step_sha256'] for n in names}):
        path=sources[digest]
        selected={n for n in names if build['body_revisions'][n]['step_sha256']==digest}
        original=native_shapes(path)
        if len(original)==len(selected)==1:
            original={next(iter(selected)):next(iter(original.values()))}
        assert selected<=set(original)
        for name in sorted(selected):
            JOBS.append((name,original[name],native[name]))
    # A shared exact root placement is a common rigid left factor. Cancelling
    # it leaves the two byte-identified native prototypes, with no rounded
    # matrices or inferred symmetry. Different root placements get no reuse.
    prototypes=[]
    def local_digest(shape):
        for previous,digest in prototypes:
            if shape.wrapped.IsPartner(previous) and shape.wrapped.Orientation()==previous.Orientation():
                return digest
        digest=hashlib.sha256(_shape_brep_bytes(shape)).hexdigest()
        prototypes.append((shape.wrapped,digest))
        return digest
    original_jobs=list(JOBS)
    JOBS.clear()
    groups={}
    for name,source,exported in original_jobs:
        if np.array_equal(placement(source),placement(exported)):
            key=('common_exact_root_placement',local_digest(source),local_digest(exported))
        else:
            key=('no_reuse',name)
        if key not in groups:
            groups[key]=len(JOBS)
            JOBS.append((name,source,exported))
            MEMBERS.append([])
        MEMBERS[groups[key]].append(name)
    output=HERE/('native_r13_export_material_probe.json' if args.sample else 'native_r13_export_material_gate.json')
    group_rows=[]
    if output.exists():
        saved=json.loads(output.read_text())
        if saved.get('input_sha256')==inputs and saved.get('proof_members')==MEMBERS:
            group_rows=saved.get('group_rows',[])
    completed={r['body'] for r in group_rows}
    pending=[i for i,job in enumerate(JOBS) if job[0] not in completed]
    print('EXPORT MATERIAL GROUPS',len(original_jobs),'occurrences',len(JOBS),'exact classes',len(pending),'pending',flush=True)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:
        for row in pool.imap_unordered(check,pending):
            group_rows.append(row)
            output.write_text(json.dumps(dict(scope=__doc__,input_sha256=inputs,group_rows=group_rows,
                               proof_members=MEMBERS,expected_count=len(original_jobs),
                               expected_proof_count=len(JOBS),complete=False,pass_=False),indent=2)+'\n')
    by_representative={r['body']:r for r in group_rows}
    rows=[]
    for (name,_,_),members in zip(JOBS,MEMBERS):
        proof=by_representative[name]
        for member in members:
            rows.append(dict(proof,body=member,proof_representative=name))
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,rows=rows,group_rows=group_rows,proof_members=MEMBERS,
                expected_count=len(original_jobs),expected_proof_count=len(JOBS),
                full_export_coverage=not args.sample,changed_during_audit=changed,
                complete=not changed,pass_=not changed and len(rows)==len(original_jobs) and all(r['pass_'] for r in rows))
    report['pass']=report.pop('pass_')
    output.write_text(json.dumps(report,indent=2)+'\n')
    assert report['pass']


if __name__=='__main__':
    main()
