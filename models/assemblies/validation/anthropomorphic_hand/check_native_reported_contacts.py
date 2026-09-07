"""Reproduce reported contacts directly from exported STEP occurrences.

This diagnoses one worst reported pose per rigid pair and every reported tendon
contact. It is not an all-pose clearance certificate and never replaces one.
The public scene reader preserves occurrence labels while parsing native STEP.
"""
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from cadgen.step_scene import load_step_scene, scene_occurrence_shape
from build123d.importers import topods_lut
from build123d.topology import downcast
from lib.assembly import matrix_location
from lib.finger_routing import transform_path
from lib.layout import assembled_transforms
from lib.transport_guide import path_wire
from lib.phalanx_r5_boolean import common
from path_solid_clearance import boundary_separation


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_shapes(path):
    scene = load_step_scene(Path(path))
    shapes = {}
    stack = list(scene.roots)
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.prototype_key is None:
            continue
        name = str(node.name or node.source_name).strip()
        assert name not in shapes, ('ambiguous occurrence', path, name)
        raw = downcast(scene_occurrence_shape(scene, node))
        shape = topods_lut[type(raw)](raw)
        shape.label = name
        shapes[name] = shape
    return shapes


def main():
    rigid_file = HERE / 'final_rigid_delta_gate.json'
    tendon_file = HERE / 'final_static_tendon_solids_gate.json'
    rigid = json.loads(rigid_file.read_text())
    tendon = json.loads(tendon_file.read_text())
    manifest_file = HERE / 'static_route_packet_manifest.json'
    manifest = json.loads(manifest_file.read_text())
    assert not rigid['changed_during_audit'] and not tendon['changed_during_audit']
    inputs = {str(p): sha(p) for p in (rigid_file, tendon_file, manifest_file)}
    sources = {digest: path for path, digest in rigid['input_sha256'].items()
               if path.endswith('.step')}
    native = {}
    checked = set()
    def shape(name):
        revision = rigid['body_revisions'][name]
        digest = revision['step_sha256']
        path = sources[digest]
        assert sha(path) == digest, ('source changed', path)
        inputs[path] = digest
        if digest not in native:
            print('READ NATIVE', path, flush=True)
            native[digest] = native_shapes(path)
            expected = {n for n, r in rigid['body_revisions'].items() if r['step_sha256'] == digest}
            # A standalone STEP uses the export's product name; the registry
            # gives that sole product its semantic name in the parent assembly.
            if len(expected) == len(native[digest]) == 1 and set(native[digest]) != expected:
                product_name, product = next(iter(native[digest].items()))
                occurrence_name = next(iter(expected))
                print('SINGLE PRODUCT NAME', product_name, '->', occurrence_name, flush=True)
                native[digest] = {occurrence_name: product}
        assert name in native[digest], ('missing native occurrence', name, path)
        if name not in checked:
            item = native[digest][name]
            assert item.solids() and item.volume > 0, ('non-solid native occurrence', path, name)
            checked.add(name)
        return native[digest][name]

    report = {'scope': __doc__.strip(), 'complete': False,
              'input_sha256': inputs, 'tendon_contacts': [], 'rigid_contacts': []}
    out = HERE / 'native_reported_contacts.json'
    def save():
        out.write_text(json.dumps(report, indent=2) + '\n')

    packets = {row['label']: row for row in manifest['rows']}
    for row in tendon['rows']:
        for hit in row['collisions']:
            packet_path = Path(packets[row['sample']]['file'])
            inputs[str(packet_path)] = sha(packet_path)
            packet = json.loads(gzip.decompress(packet_path.read_bytes()))
            assert packet['source_sha256'] == manifest['source_sha256']
            route = next(r for r in packet['routes'] if r['name'] == hit['tendon'])
            group = next(g for g in route['groups'] if g['label'] == hit['group'])
            frame = rigid['body_revisions'][hit['body']]['frame']
            local = transform_path(group['path'], np.linalg.inv(assembled_transforms(row['pose'])[frame]))
            body = shape(hit['body'])
            wire = path_wire(local)
            distance = wire.distance_to(body)
            radius = hit['path_outer_radius_mm']
            result = {'sample': row['sample'], 'pose': row['pose'], **hit,
                      'native_centerline_distance_mm': distance,
                      'native_surface_gap_mm': distance-radius,
                      'native_collision': distance < radius-1e-7}
            if result['native_collision']:
                result['boundary_proof'] = boundary_separation(wire, body, radius)
                if result['boundary_proof']['proven_separated']:
                    result['native_collision'] = False
            report['tendon_contacts'].append(result)
            print('TENDON', json.dumps(result), flush=True)
            save()

    worst = {}
    for row in rigid['rows']:
        for hit in row['collisions']:
            pair = tuple(sorted((hit['a'], hit['b'])))
            if pair not in worst or hit['intersection_mm3'] > worst[pair][1]['intersection_mm3']:
                worst[pair] = row, hit
    for pair, (row, hit) in sorted(worst.items()):
        fk = assembled_transforms(row['pose'])
        a, b = pair
        sa = matrix_location(fk[rigid['body_revisions'][a]['frame']]) * shape(a)
        sb = matrix_location(fk[rigid['body_revisions'][b]['frame']]) * shape(b)
        intersection = common(sa, sb)
        volume = sum(s.volume for s in intersection.solids())
        result = {'a': a, 'b': b, 'sample': row['sample'], 'pose': row['pose'],
                  'cached_intersection_mm3': hit['intersection_mm3'],
                  'native_intersection_mm3': volume, 'native_collision': volume > 1e-7}
        report['rigid_contacts'].append(result)
        print('RIGID', json.dumps(result), flush=True)
        save()
    report['changed_during_audit'] = [path for path, digest in inputs.items() if sha(path) != digest]
    report['complete'] = not report['changed_during_audit']
    report['native_rigid_collision_count'] = sum(r['native_collision'] for r in report['rigid_contacts'])
    report['native_tendon_collision_count'] = sum(r['native_collision'] for r in report['tendon_contacts'])
    save()
    assert report['complete'], report['changed_during_audit']
    print('DIAGNOSTIC COMPLETE', report['native_rigid_collision_count'], report['native_tendon_collision_count'], flush=True)


if __name__ == '__main__':
    main()
