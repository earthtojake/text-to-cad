"""Native attachment graph for all 32 remade middle-phalanx support bodies.

The existing 0.025 mm seating/thread-fit contract applies. Every support must
connect to the actual new phalanx through proved native distances. Interference
and strict-solid checks are independent gates.
"""
import itertools
import json
from pathlib import Path

from native_hand_registry import HERE, sha
from check_native_reported_contacts import native_shapes
from check_full_route_bodies import placed_bounds
from lib.assembly import Body


def main():
    path = HERE.parents[1] / 'STEP/anthropomorphic_hand/phalanx_continuous_representative_r5.step'
    shapes = native_shapes(path)
    assert len(shapes) == 33
    shapes = {name: shape.solids()[0] for name, shape in shapes.items() if len(shape.solids()) == 1}
    assert len(shapes) == 33
    for name, shape in shapes.items():
        shape.label = name
    bodies = [Body(shape, 'middle_mcp_flexion', 'middle', 'guide_mount') for shape in shapes.values()]
    bounds = placed_bounds(bodies)
    edges = []
    for a, b in itertools.combinations(sorted(shapes), 2):
        ba, bb = bounds[a], bounds[b]
        if any(getattr(ba.max, k) < getattr(bb.min, k) - .025001 or
               getattr(bb.max, k) < getattr(ba.min, k) - .025001 for k in ('X', 'Y', 'Z')):
            continue
        distance = shapes[a].distance_to(shapes[b])
        if distance <= .025:
            edges.append(dict(a=a, b=b, distance_mm=distance))
            print('ATTACHMENT', a, b, distance, flush=True)
    anchor = 'middle_proximal_frame'
    reached = {anchor}
    while True:
        new = reached | {e['a'] for e in edges if e['b'] in reached} | {e['b'] for e in edges if e['a'] in reached}
        if new == reached:
            break
        reached = new
    inputs = {str(p): sha(p) for p in (path, Path(__file__), HERE / 'check_native_reported_contacts.py',
                                       HERE / 'check_full_route_bodies.py')}
    report = dict(scope=__doc__, input_sha256=inputs, anchor=anchor, frame='middle_mcp_flexion',
                  body_count=33, contact_tolerance_mm=.025, contact_edges=edges,
                  unattached=sorted(set(shapes) - reached), complete=True, pass_=len(reached) == 33)
    report['pass'] = report.pop('pass_')
    (HERE / 'native_finger_attachments_r5_gate.json').write_text(json.dumps(report, indent=2) + '\n')
    print('NATIVE FINGER ATTACHMENTS', report['pass'], report['unattached'], flush=True)
    assert report['pass']


if __name__ == '__main__':
    main()
