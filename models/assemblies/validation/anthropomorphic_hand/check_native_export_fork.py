"""Audit the actual R13 wrist fork against every native neighbour and route.

STEP re-export changed this body's trim representation. This fresh delta uses
the final exported shapes directly; it does not claim source/export equality.
All 225 static poses include physical actuator payout. Existing collision
thresholds remain 1e-7 mm^3 for rigid solids and the unchanged route validator.
"""
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopTools import TopTools_ListOfShape

from check_native_reported_contacts import native_shapes
from check_full_route_bodies import audit as route_audit, placed_bounds
from rigid_separation_filter import separation
from lib.assembly import Body, posed_bodies
from lib.actuator_kinematics import apply_actuator_motion
from lib.layout import TENDONS

HERE = Path(__file__).resolve().parent
NAME = 'wrist_fixed_bearing_fork'
PREFIX = 'native_r13_export_fork'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix(shape):
    tr = shape.wrapped.Location().Transformation()
    out = np.eye(4)
    out[:3, :] = [[tr.Value(r, c) for c in range(1, 5)] for r in range(1, 4)]
    return out


def intersection(a, b):
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(a.wrapped)
    tools.Append(b.wrapped)
    op = BRepAlgoAPI_Common()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetNonDestructive(True)
    op.Build()
    assert op.IsDone(), 'Native intersection failed'
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(op.Shape(), props)
    return float(props.Mass())


def disjoint(a, b):
    return any(getattr(a.max, k) < getattr(b.min, k)-1e-8 or
               getattr(b.max, k) < getattr(a.min, k)-1e-8 for k in ('X', 'Y', 'Z'))


def main(loaded_shapes=None):
    document = HERE.parents[1]/'STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step'
    frame_path = HERE/'mechanical_candidate_r13_frames.json'
    packet_path = HERE/'payout_static_route_packet_manifest.json'
    metadata = json.loads(frame_path.read_text())
    manifest = json.loads(packet_path.read_text())
    assert manifest['complete'] and len(manifest['rows']) == 225
    lib = HERE.parents[1]/'src/anthropomorphic_hand/lib'
    paths = [Path(__file__), document, frame_path, packet_path,
             *[HERE/n for n in ('check_native_reported_contacts.py',
                'check_full_route_bodies.py', 'path_solid_clearance.py',
                'rigid_separation_filter.py', 'check_hand_route_pairs.py',
                'check_middle_hardware_paths.py')],
             *lib.glob('*.py')]
    inputs = {str(p): sha(p) for p in paths}
    for p, h in manifest['input_sha256'].items():
        assert sha(p) == h
        inputs[p] = h
    shapes = native_shapes(document) if loaded_shapes is None else loaded_shapes
    assert len(shapes) == len(metadata) == 3259
    assert set(shapes) == {r['name'] for r in metadata}
    bodies = [Body(shapes[r['name']], r['frame'], r['system'], r['kind'])
              for r in metadata if r['frame'] != 'variable']
    assert len(bodies) == len({b.name for b in bodies}) == 3041
    target = next(b for b in bodies if b.name == NAME)
    assert target.frame == 'forearm'
    control = intersection(target.shape, target.shape)
    assert control > 800 and abs(control-target.shape.volume) < 1e-6
    # Exact relative placements are the only cross-pose rigid cache keys.
    rigid_cache, route_cache, rows = {}, {}, []
    report = dict(scope=__doc__, input_sha256=inputs,
                  document_sha256=sha(document), changed_names=[NAME],
                  body_count=3041, expected_pose_count=225,
                  positive_control_volume_mm3=control, rows=rows,
                  complete=False, pass_=False)
    out = HERE/f'{PREFIX}_gate.json'

    def save():
        temp = out.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2)+'\n')
        temp.replace(out)

    for sample in manifest['rows']:
        path = Path(sample['file'])
        assert sha(path) == sample['file_sha256']
        packet = json.loads(gzip.decompress(path.read_bytes()))
        assert packet['source_sha256'] == sample['source_sha256']
        assert packet['pose'] == sample['pose'] and len(packet['routes']) == 48
        moved, _, active = apply_actuator_motion(
            posed_bodies(bodies, sample['pose']), TENDONS, packet['actuator_angles_rad'])
        boxes = placed_bounds(moved)
        fork = next(b for b in moved if b.name == NAME)
        inverse = np.linalg.inv(matrix(fork.shape))
        collisions, native, reused, aabb = [], 0, 0, 0
        for neighbour in moved:
            if neighbour.name == NAME:
                continue
            if disjoint(boxes[NAME], boxes[neighbour.name]):
                aabb += 1
                continue
            relative = inverse @ matrix(neighbour.shape)
            key = (neighbour.name, tuple(float(x).hex() for x in relative.ravel()))
            if key in rigid_cache:
                volume = rigid_cache[key]
                reused += 1
            else:
                gap = separation(fork.shape.wrapped, neighbour.shape.wrapped)
                volume = 0. if gap is not None else intersection(fork.shape, neighbour.shape)
                rigid_cache[key] = volume
                native += 1
            if volume > 1e-7:
                collisions.append(dict(a=NAME, b=neighbour.name, intersection_mm3=volume))
        assert aabb+native+reused == 3040
        routes = route_audit(packet['routes'], [target], sample['pose'], cache=route_cache)
        rows.append(dict(sample=sample['label'], pose=sample['pose'],
                         aabb_separated_pairs=aabb, native_pairs=native,
                         exact_placement_reuse=reused, moving_actuator_count=len(active),
                         collisions=collisions, routes=routes,
                         pass_=not collisions and routes['pass']))
        save()
        print('FINAL EXPORT FORK', sample['label'], rows[-1]['pass_'], flush=True)
    changed = [p for p, h in inputs.items() if sha(p) != h]
    report.update(complete=not changed, changed_during_audit=changed,
                  pass_=not changed and len(rows) == 225 and all(r['pass_'] for r in rows))
    save()
    assert report['pass_'], 'Actual exported fork did not pass'
    return report


if __name__ == '__main__':
    main()
