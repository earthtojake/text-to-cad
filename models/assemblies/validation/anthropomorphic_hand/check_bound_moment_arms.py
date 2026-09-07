"""Bound neutral virtual-work matrix for all 24 axes and 48 hand-side routes.

This measures terminal-side actuation at neutral. Wrist transport compensation
and the full static collision range have separate certificates.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / 'src/anthropomorphic_hand'
sys.path.insert(0, str(SOURCE))
from lib.hand_routing import hand_side_routes
from lib.layout import JOINTS, TENDONS
from lib.path_analysis import path_length


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    # Freeze the whole local route implementation before evaluating any path.
    inputs = {str(p): sha(p) for p in [Path(__file__), *sorted((SOURCE/'lib').glob('*.py'))]}
    epsilon = .001
    tolerance = 1e-4
    names = {t['name'] for t in TENDONS}
    rows = []
    for joint in JOINTS:
        a = max(joint.limits[0], -epsilon)
        b = min(joint.limits[1], epsilon)
        assert a < b
        left = {r['name']: path_length(r['path']) for r in hand_side_routes({joint.name: a})}
        right = {r['name']: path_length(r['path']) for r in hand_side_routes({joint.name: b})}
        assert set(left) == set(right) == names
        entries = []
        for tendon in TENDONS:
            measured = -(right[tendon['name']] - left[tendon['name']]) / math.radians(b-a)
            expected = tendon['sign']*joint.drive_radius if tendon['joint'] == joint.name else 0.
            entries.append(dict(tendon=tendon['name'], moment_arm_mm=measured,
                                expected_mm=expected, pass_=abs(measured-expected) < tolerance))
        row = dict(joint=joint.name, interval_degrees=[a,b], tendons=entries,
                   positive_drive=any(e['moment_arm_mm'] > 1 for e in entries),
                   negative_drive=any(e['moment_arm_mm'] < -1 for e in entries))
        row['pass'] = row['positive_drive'] and row['negative_drive'] and all(e['pass_'] for e in entries)
        rows.append(row)
        print('MOMENT MATRIX', joint.name, row['pass'], flush=True)
    changed = [p for p,h in inputs.items() if sha(p) != h]
    result = dict(scope=__doc__, input_sha256=inputs, joints=rows, joint_count=len(rows),
                  tendon_count=len(names), tolerance_mm=tolerance,
                  changed_during_audit=changed, complete=not changed and len(rows)==24)
    result['pass'] = result['complete'] and len(names)==48 and all(r['pass'] for r in rows)
    (HERE/'native_r13_neutral_moment_arm_gate.json').write_text(json.dumps(result, indent=2)+'\n')
    assert result['pass']


if __name__ == '__main__':
    main()
