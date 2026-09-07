"""Native full-range delta for the continuous middle phalanx and PIP collars.

The 33 replacement bodies and two collars are tested together against every
rigid assembly neighbour and all 48 solved payout routes at 225 static poses.
This is a candidate gate; independent aesthetic acceptance remains separate.
"""
import argparse
import gzip
import json
import multiprocessing
from pathlib import Path

from native_hand_registry import HERE, native_current_bodies, sha
from check_native_reported_contacts import native_shapes
from check_native_assembly_interference import audit as rigid_audit
from check_full_route_bodies import audit as route_audit, placed_bounds
from lib.assembly import Body, posed_bodies
from lib.actuator_kinematics import apply_actuator_motion
from lib.layout import TENDONS

PREFIX = 'native_finger_finish_r5_v2'
PREFIXES = ('middle_mcp_outlet_comb', 'middle_pip_inlet_comb', 'middle_pip_drive_guide')
BODIES = NEW = INPUTS = MANIFEST = None


def tuples(value):
    return tuple(tuples(v) for v in value) if isinstance(value, list) else value


def disjoint(a, b):
    return any(getattr(a.max, axis) < getattr(b.min, axis) - 1e-8 or
               getattr(b.max, axis) < getattr(a.min, axis) - 1e-8
               for axis in ('X', 'Y', 'Z'))


def partition(index):
    samples = MANIFEST['rows'][index::4]
    checkpoint = HERE / f'{PREFIX}_checkpoint_{index}.json.gz'
    rigid_cache, route_cache, rows = {}, {}, []
    if checkpoint.exists():
        saved = json.loads(gzip.decompress(checkpoint.read_bytes()))
        if saved['input_sha256'] == INPUTS:
            rows = saved['rows']
            rigid_cache = {tuples(k): v for k, v in saved['rigid_cache']}
            route_cache = {tuples(k): v for k, v in saved['route_cache']}
    for row, sample in zip(rows, samples):
        assert (row['sample'], row['pose']) == (sample['label'], sample['pose'])

    def save(_=None):
        data = dict(input_sha256=INPUTS, rows=rows,
                    rigid_cache=list(rigid_cache.items()), route_cache=list(route_cache.items()))
        temp = checkpoint.with_suffix('.tmp')
        temp.write_bytes(gzip.compress(json.dumps(data, separators=(',', ':')).encode()))
        temp.replace(checkpoint)

    for sample in samples[len(rows):]:
        path = Path(sample['file'])
        assert sha(path) == sample['file_sha256']
        packet = json.loads(gzip.decompress(path.read_bytes()))
        assert packet['source_sha256'] == sample['source_sha256'] and packet['pose'] == sample['pose']
        assert len(packet['routes']) == 48
        placed = posed_bodies(BODIES, sample['pose'])
        rigid = rigid_audit(placed, HERE / f'{PREFIX}_rigid_live_{index}.json',
                            cache=rigid_cache, changed_names={b.name for b in NEW},
                            pose=sample['pose'], on_progress=save)
        # The hand-frame audit keeps the forearm at zero payout. Explicit
        # native AABB separation covers every new-body/rotating-actuator pair.
        moved, _, active = apply_actuator_motion(placed, TENDONS, packet['actuator_angles_rad'])
        boxes = placed_bounds(moved)
        unresolved = [(a.name, b.name) for a in NEW for b in moved
                      if b.name in active and not disjoint(boxes[a.name], boxes[b.name])]
        assert not unresolved, ('Payout needs exact follow-up', unresolved)
        routes = route_audit(packet['routes'], NEW, sample['pose'], cache=route_cache)
        rows.append(dict(sample=sample['label'], pose=sample['pose'], rigid=rigid,
                         routes=routes, payout_aabb_pairs=len(NEW) * len(active),
                         pass_=rigid['pass'] and routes['pass']))
        save()
        (HERE / f'{PREFIX}_partition_{index}.json').write_text(json.dumps(
            dict(rows=rows, complete=len(rows) == len(samples)), indent=2) + '\n')
        print('FINGER FINISH', sample['label'], rows[-1]['pass_'], flush=True)
    return rows


def main():
    global BODIES, NEW, INPUTS, MANIFEST
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    BODIES, INPUTS = native_current_bodies(include_reliefs=True)
    folder = HERE.parents[1] / 'STEP/anthropomorphic_hand'
    # Include the latest native mechanical repairs in this candidate context.
    for filename in ('fingertip_bridge_repair_review.step', 'radial_bank_screw_clearance_candidate.step',
                     'thumb_reaction_arm_clearance_r5.step'):
        path = folder / filename
        shapes = native_shapes(path)
        for body in BODIES:
            if body.name in shapes:
                body.shape = shapes.pop(body.name)
                body.source_path, body.source_sha256 = str(path), sha(path)
        assert not shapes
        INPUTS[str(path)] = sha(path)
    path = folder / 'phalanx_continuous_representative_r5.step'
    shapes = native_shapes(path)
    assert len(shapes) == 33
    removed = [b for b in BODIES if b.name == 'middle_proximal_frame' or b.name.startswith(PREFIXES)]
    assert len(removed) == 33 and {b.frame for b in removed} == {'middle_mcp_flexion'}
    BODIES = [b for b in BODIES if b not in removed]
    NEW = []
    for name, shape in shapes.items():
        assert name == 'middle_proximal_frame' or name.startswith(PREFIXES)
        body = Body(shape, 'middle_mcp_flexion', 'middle', 'phalanx' if name == 'middle_proximal_frame' else 'guide_mount')
        body.source_path, body.source_sha256 = str(path), sha(path)
        NEW.append(body)
    INPUTS[str(path)] = sha(path)
    path = folder / 'pulley_hub_review.step'
    shapes = native_shapes(path)
    assert len(shapes) == 2
    for name, shape in shapes.items():
        body = Body(shape, 'middle_pip', 'middle', 'hub_spacer')
        body.source_path, body.source_sha256 = str(path), sha(path)
        NEW.append(body)
    INPUTS[str(path)] = sha(path)
    BODIES += NEW
    assert len(BODIES) == len({b.name for b in BODIES}) == 3041
    for body in NEW:
        name = body.name
        assert len(body.shape.solids()) == 1
        body.shape = body.shape.solids()[0]
        body.shape.label = name
    assert len({b.name for b in NEW}) == 35 and all(b.name for b in NEW)
    assert len({b.name for b in BODIES}) == 3041 and all(b.name for b in BODIES)
    manifest_path = HERE / 'payout_static_route_packet_manifest.json'
    MANIFEST = json.loads(manifest_path.read_text())
    assert MANIFEST['complete'] and len(MANIFEST['rows']) == 225
    assert all(sha(p) == h for p, h in MANIFEST['input_sha256'].items())
    INPUTS.update(MANIFEST['input_sha256'])
    lib = HERE.parents[1] / 'src/anthropomorphic_hand/lib'
    paths = [Path(__file__), manifest_path,
             *[HERE / n for n in ('check_native_assembly_interference.py', 'rigid_separation_filter.py',
                                  'rigid_pose_cache.py', 'check_full_route_bodies.py', 'path_solid_clearance.py',
                                  'check_hand_route_pairs.py', 'check_middle_hardware_paths.py')],
             *[lib / n for n in ('assembly.py', 'layout.py', 'finger_routing.py', 'transport_guide.py',
                                 'path_analysis.py', 'actuator_kinematics.py')]]
    INPUTS.update({str(p): sha(p) for p in paths})
    revisions = {b.name: dict(step_sha256=b.source_sha256, frame=b.frame) for b in BODIES}
    assert len(revisions) == len(BODIES) == 3041
    placed_bounds(BODIES)
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:
        partitions = pool.map(partition, range(4))
    rows = [row for batch in partitions for row in batch]
    assert len(rows) == 225
    changed = [p for p, h in INPUTS.items() if sha(p) != h]
    report = dict(scope=__doc__, input_sha256=INPUTS, body_revisions=revisions,
                  changed_names=sorted(b.name for b in NEW), removed_names=sorted(b.name for b in removed),
                  rows=rows, sample_count=225, body_count=3041, complete=not changed,
                  changed_during_audit=changed, pass_=not changed and all(r['pass_'] for r in rows))
    report['pass'] = report.pop('pass_')
    (HERE / f'{PREFIX}_gate.json').write_text(json.dumps(report, indent=2) + '\n')
    assert report['pass']


if __name__ == '__main__':
    main()
