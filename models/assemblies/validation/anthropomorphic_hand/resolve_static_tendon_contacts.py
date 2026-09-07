"""Supplement an unchanged complete tendon audit with exact contact rechecks.

Only previously failing path/body pairs are rerun. Every prior passing pair
inherits its original certificate, whose hash and immutable STEP inputs are
recorded. This does not certify rigid/rigid clearance or later geometry changes.
"""
import copy
import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'src/anthropomorphic_hand'))
from cadgen import read_step
from lib.assembly import Body
from lib.layout import TENDONS
from check_full_route_bodies import audit


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def leaves(shape):
    return [s for child in shape.children for s in leaves(child)] if shape.children else [shape]


def main():
    baseline_path = HERE / 'final_static_tendon_solids_gate.json'
    baseline = json.loads(baseline_path.read_text())
    manifest_path = HERE / 'static_route_packet_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    assert not baseline['changed_during_audit']
    assert baseline['source_sha256'] == manifest['source_sha256']
    assert baseline['sample_count'] == len(baseline['rows']) == len(manifest['rows']) == 225
    paths = {digest: path for path, digest in baseline['inputs'].items() if path.endswith('.step')}
    inputs = {**baseline['inputs'], str(baseline_path): sha(baseline_path), str(manifest_path): sha(manifest_path)}
    for filename in ('resolve_static_tendon_contacts.py', 'check_full_route_bodies.py', 'path_solid_clearance.py'):
        path = HERE / filename
        inputs[str(path)] = sha(path)
    assert all(sha(path) == digest for path, digest in inputs.items()), 'changed audit input'
    report = copy.deepcopy(baseline)
    report['scope'] = __doc__.strip()
    report['original_certificate_sha256'] = sha(baseline_path)
    report['contact_rechecks'] = []
    native = {}
    for row, sample in zip(report['rows'], manifest['rows']):
        assert row['sample'] == sample['label'] and row['pose'] == sample['pose']
        assert len(row['tendon_table']) == 48
        assert {r['tendon'] for r in row['tendon_table']} == {t['name'] for t in TENDONS}
        table_contacts = [c for t in row['tendon_table'] for c in t['collisions']]
        assert sorted(json.dumps(c, sort_keys=True) for c in table_contacts) == sorted(
            json.dumps(c, sort_keys=True) for c in row['collisions'])
        prior = list(row['collisions'])
        if not prior:
            assert row['pass'] and all(t['clear'] and not t['collisions'] for t in row['tendon_table'])
            continue
        packet_path = Path(sample['file'])
        inputs[str(packet_path)] = sha(packet_path)
        packet = json.loads(gzip.decompress(packet_path.read_bytes()))
        assert packet['source_sha256'] == manifest['source_sha256']
        unresolved = []
        for hit in prior:
            revision = report['body_revisions'][hit['body']]
            digest = revision['sha256']
            if digest not in native:
                items = leaves(read_step(paths[digest]))
                assert len({s.label for s in items}) == len(items)
                native[digest] = {s.label: s for s in items}
            shape = native[digest][hit['body']]
            body = Body(shape, revision['frame'], 'clearance_recheck', hit['body_kind'])
            route = next(r for r in packet['routes'] if r['name'] == hit['tendon'])
            group = next(g for g in route['groups'] if g['label'] == hit['group'])
            result = audit([{**route, 'groups': [group]}], [body], row['pose'])
            report['contact_rechecks'].append({'sample': row['sample'], 'original_contact': hit, **result})
            if not result['pass']:
                unresolved.append(hit)
        row['collisions'] = unresolved
        row['pass'] = not unresolved
        for tendon in row['tendon_table']:
            tendon['collisions'] = [c for c in unresolved if c['tendon'] == tendon['tendon']]
            tendon['clear'] = not tendon['collisions']
    report['inputs'] = inputs
    report['changed_during_audit'] = [p for p, digest in inputs.items() if sha(p) != digest]
    report['pass'] = not report['changed_during_audit'] and all(r['pass'] for r in report['rows'])
    out = HERE / 'final_static_tendon_solids_resolved_gate.json'
    out.write_text(json.dumps(report, indent=2)+'\n')
    print('RESOLVED STATIC TENDON AUDIT', report['pass'], len(report['contact_rechecks']), 'rechecked contacts')
    assert report['pass']


if __name__ == '__main__':
    main()
