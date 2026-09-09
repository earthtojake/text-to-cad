"""Fresh final-export checks for rigid bodies lacking a completed equality proof.

The wrist fork has its own complete direct-export delta. This audit covers the
other 46 rigid occurrences against all 3041 actual R13 rigid occurrences and
48 solved tendon routes at all 225 poses, with physical actuator payout.
No boundary-record match substitutes for a collision check in this delta.
"""
import argparse
import gzip
import json
import multiprocessing
from pathlib import Path

import numpy as np
from check_native_export_fork import sha, matrix, intersection, HERE
from check_native_reported_contacts import native_shapes
from check_full_route_bodies import audit as route_audit, placed_bounds
from rigid_separation_filter import separation
from rigid_pose_cache import relative_pose_key
from lib.assembly import Body, posed_bodies
from lib.actuator_kinematics import apply_actuator_motion
from lib.layout import TENDONS

PREFIX = 'native_r13_export_rigid_delta'
BODIES = TARGETS = MANIFEST = INPUTS = None
PARTITIONS = 4


def tuples(value):
    return tuple(tuples(x) for x in value) if isinstance(value, list) else value


def partition(index):
    selected = MANIFEST['rows'][index::PARTITIONS]
    checkpoint = HERE/f'{PREFIX}_checkpoint_{index}.json.gz'
    rows, rigid_cache, route_cache = [], {}, {}
    if checkpoint.exists():
        saved = json.loads(gzip.decompress(checkpoint.read_bytes()))
        if saved['input_sha256'] == INPUTS:
            rows = saved['rows']
            rigid_cache = {tuples(k): v for k, v in saved['rigid_cache']}
            route_cache = {tuples(k): v for k, v in saved['route_cache']}
    for row, sample in zip(rows, selected):
        assert (row['sample'], row['pose']) == (sample['label'], sample['pose'])

    def save():
        temp = checkpoint.with_suffix('.tmp')
        temp.write_bytes(gzip.compress(json.dumps(dict(
            input_sha256=INPUTS, rows=rows, rigid_cache=list(rigid_cache.items()),
            route_cache=list(route_cache.items())), separators=(',', ':')).encode()))
        temp.replace(checkpoint)
        (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(
            rows=rows, complete=len(rows) == len(selected),
            pass_=all(r['pass_'] for r in rows)), indent=2)+'\n')

    target_names = {b.name for b in TARGETS}
    for sample in selected[len(rows):]:
        path = Path(sample['file'])
        assert sha(path) == sample['file_sha256']
        packet = json.loads(gzip.decompress(path.read_bytes()))
        assert packet['source_sha256'] == sample['source_sha256']
        assert packet['pose'] == sample['pose'] and len(packet['routes']) == 48
        moved, aliases, active = apply_actuator_motion(
            posed_bodies(BODIES, sample['pose']), TENDONS, packet['actuator_angles_rad'])
        boxes = placed_bounds(moved)
        lows = np.asarray([list(boxes[b.name].min) for b in moved])
        highs = np.asarray([list(boxes[b.name].max) for b in moved])
        indices = {b.name: i for i, b in enumerate(moved)}
        changed = np.asarray([b.name in target_names for b in moved])
        order = np.arange(len(moved))
        collisions, aabb, native, reused = [], 0, 0, 0
        for name in sorted(target_names):
            i = indices[name]
            a = moved[i]
            eligible = (~changed | (order > i)) & (order != i)
            separated = np.any((highs < lows[i]-1e-8) | (lows > highs[i]+1e-8), axis=1)
            aabb += int(np.count_nonzero(eligible & separated))
            for j in np.flatnonzero(eligible & ~separated):
                b = moved[j]
                if a.name not in aliases and b.name not in aliases:
                    key = relative_pose_key(a.name, a.frame, b.name, b.frame, sample['pose'])
                else:
                    relative = np.linalg.inv(matrix(a.shape)) @ matrix(b.shape)
                    key = ('physical_relative_placement', a.name, b.name,
                           tuple(float(x).hex() for x in relative.ravel()))
                if key in rigid_cache:
                    volume = rigid_cache[key]
                    reused += 1
                else:
                    gap = separation(a.shape.wrapped, b.shape.wrapped)
                    volume = 0. if gap is not None else intersection(a.shape, b.shape)
                    rigid_cache[key] = volume
                    native += 1
                if volume > 1e-7:
                    collisions.append(dict(a=a.name, b=b.name, intersection_mm3=volume))
            if collisions:
                print('FINAL EXPORT DELTA CONTACT', sample['label'], collisions[-1], flush=True)
        expected_pairs = len(TARGETS)*(len(moved)-len(TARGETS)) + len(TARGETS)*(len(TARGETS)-1)//2
        assert aabb+native+reused == expected_pairs
        routes = route_audit(packet['routes'], TARGETS, sample['pose'], cache=route_cache)
        rows.append(dict(sample=sample['label'], pose=sample['pose'],
                         pair_count=expected_pairs, aabb_separated_pairs=aabb,
                         native_pairs=native, exact_pose_reuse=reused,
                         moving_actuator_count=len(active), collisions=collisions,
                         routes=routes, pass_=not collisions and routes['pass']))
        save()
        print('FINAL EXPORT DELTA', sample['label'], rows[-1]['pass_'], flush=True)
    return rows


def main():
    global BODIES, TARGETS, MANIFEST, INPUTS
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    document = HERE.parents[1]/'STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step'
    frame_path = HERE/'mechanical_candidate_r13_frames.json'
    packet_path = HERE/'payout_static_route_packet_manifest.json'
    evidence_path = HERE/'native_r13_export_records.json'
    frames = json.loads(frame_path.read_text())
    evidence = json.loads(evidence_path.read_text())
    assert evidence['complete'] and not evidence['changed_during_audit']
    assert evidence['occurrence_count'] == 3259 and evidence['document_sha256'] == sha(document)
    names = {n for r in evidence['rows'] if r['status'] != 'completed_zero_face_native_differences'
             for n in r['members']}
    MANIFEST = json.loads(packet_path.read_text())
    assert MANIFEST['complete'] and len(MANIFEST['rows']) == 225
    lib = HERE.parents[1]/'src/anthropomorphic_hand/lib'
    paths = [Path(__file__), document, frame_path, packet_path, evidence_path,
             *[HERE/n for n in ('check_native_export_fork.py', 'check_native_reported_contacts.py',
                'check_full_route_bodies.py', 'path_solid_clearance.py',
                'rigid_separation_filter.py', 'rigid_pose_cache.py',
                'check_hand_route_pairs.py', 'check_middle_hardware_paths.py')], *lib.glob('*.py')]
    INPUTS = {str(p): sha(p) for p in paths}
    for doc in (MANIFEST, evidence):
        for p, h in doc['input_sha256'].items():
            assert sha(p) == h and (p not in INPUTS or INPUTS[p] == h), p
            INPUTS[p] = h
    shapes = native_shapes(document)
    assert set(shapes) == {r['name'] for r in frames} and len(shapes) == 3259
    BODIES = [Body(shapes[r['name']], r['frame'], r['system'], r['kind'])
              for r in frames if r['frame'] != 'variable']
    assert len(BODIES) == len({b.name for b in BODIES}) == 3041
    TARGETS = [b for b in BODIES if b.name in names and b.name != 'wrist_fixed_bearing_fork']
    assert len(TARGETS) == len({b.name for b in TARGETS}) == 46
    assert all(b.frame != 'forearm' for b in TARGETS)
    assert {b.kind for b in TARGETS} == {'drive_terminal_bond_line', 'drive_terminal_ferrule', 'phalanx'}
    placed_bounds(BODIES)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:
        partitions = pool.map(partition, range(PARTITIONS))
    rows = [r for batch in partitions for r in batch]
    assert len(rows) == len({r['sample'] for r in rows}) == 225
    changed = [p for p, h in INPUTS.items() if sha(p) != h]
    report = dict(scope=__doc__, input_sha256=INPUTS, document_sha256=sha(document),
                  changed_names=sorted(b.name for b in TARGETS), body_count=3041,
                  sample_count=225, rows=rows, complete=not changed,
                  changed_during_audit=changed,
                  pass_=not changed and all(r['pass_'] for r in rows))
    (HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report, indent=2)+'\n')
    assert report['pass_']


if __name__ == '__main__':
    main()
