"""Compare exact placed native BREP payloads before reusing strict validation.

Only byte-identical geometry AND placements may inherit a completed strict
report. All other occurrences require fresh native checks. This plan itself
contains no validity verdict and does not accept an incomplete baseline.
"""
import argparse
import hashlib
import json
from pathlib import Path

from cadgen.step_scene import load_step_scene
from cadgen.interference import occurrences_from_scene
from cadgen.validity import _placed_compound
from cadgen._internal.component_package import _shape_brep_bytes


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identities(path):
    scene = load_step_scene(path)
    rows = {}
    for i, occurrence in enumerate(occurrences_from_scene(scene)):
        assert occurrence.name and occurrence.name not in rows
        payload = _shape_brep_bytes(_placed_compound([occurrence.shape]))
        rows[occurrence.name] = dict(ref=occurrence.ref, placed_brep_sha256=hashlib.sha256(payload).hexdigest())
        if i % 250 == 0:
            print('NATIVE PAYLOAD',path.name,i,flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--old',type=Path,required=True)
    parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    old_path,new_path=args.old.resolve(),args.new.resolve()
    inputs={str(p):sha(p) for p in (old_path,new_path,Path(__file__))}
    old,new=identities(old_path),identities(new_path)
    inherited=sorted(n for n,r in new.items() if n in old and r['placed_brep_sha256']==old[n]['placed_brep_sha256'])
    fresh=sorted(set(new)-set(inherited))
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    assert not changed
    report=dict(scope=__doc__,input_sha256=inputs,old_document=str(old_path),new_document=str(new_path),
                old_occurrence_count=len(old),new_occurrence_count=len(new),old=old,new=new,
                byte_identical_names=inherited,fresh_names=fresh,fresh_refs=[new[n]['ref'] for n in fresh],
                removed_names=sorted(set(old)-set(new)),complete=True,validity_verdict=None)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print('IDENTICAL',len(inherited),'FRESH',len(fresh),'REMOVED',len(report['removed_names']),flush=True)


if __name__=='__main__':
    main()
