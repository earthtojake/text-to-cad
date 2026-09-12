"""Exact neutral solid intersections, including the current universal carrier."""
import json
from pathlib import Path
import build123d as bd
from lib.universal_carrier import make_universal_carrier
from lib.finger_routing import MIDDLE,middle_finger_routes


def volume(shape):
    if shape is None:return 0.
    return shape.volume if hasattr(shape,'volume') else sum(volume(s) for s in shape)


def boxes_overlap(a,b):
    a,b=a.bounding_box(),b.bounding_box()
    return all(getattr(a.max,c)>=getattr(b.min,c) and getattr(b.max,c)>=getattr(a.min,c) for c in ('X','Y','Z'))


if __name__=='__main__':
    document=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/middle_routing_review.step')
    children=list(document.children)
    # import_step exposes shared prototype labels; authoritative source order
    # preserves per-occurrence names without confusing equal-radius pulleys.
    names=[f'middle_link_{i+1:02d}' for i in range(3)]
    names += [f'middle_{j}_{s}_drive_pulley' for j in ('mcp_abduction','mcp_flexion','pip','dip') for s in ('positive','negative')]
    for route in middle_finger_routes():
        names.append(route['name'])
        names.extend(g['label'] for g in route['groups'] if g['guide'] in ('snug_reaction_liner','fixed_curved_guide'))
    if len(names)!=len(children):raise ValueError('STEP occurrence count differs from source registry')
    for part,name in zip(children,names):part.label=name
    children.append(bd.Pos(MIDDLE.x,MIDDLE.base_y,0)*make_universal_carrier(label='middle_mcp_carrier'))
    pairs=[];tested=0
    for i,a in enumerate(children):
        for b in children[i+1:]:
            if not boxes_overlap(a,b):continue
            tested+=1;v=volume(a.intersect(b))
            if v>1e-7:pairs.append({'a':a.label,'b':b.label,'intersection_mm3':v})
    report={'parts':len(children),'solids':sum(len(c.solids()) for c in children),
            'all_valid':all(c.is_valid for c in children),'boolean_pairs_tested':tested,'collisions':pairs}
    Path(__file__).with_name('middle_neutral_solids_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if pairs:raise SystemExit(1)
