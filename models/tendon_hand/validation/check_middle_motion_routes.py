"""Full middle paths at requested one-axis samples and representative poses."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from lib.finger_routing import middle_finger_routes
from lib.layout import JOINT_BY_NAME
from check_middle_routes import route_metrics

if __name__=='__main__':
    joints=['middle_mcp_abduction','middle_mcp_flexion','middle_pip','middle_dip']
    samples=[('flat_open',{})]
    for j in joints:
        lo,hi=JOINT_BY_NAME[j].limits
        values=sorted(set(list(np.arange(lo,hi+1e-8,10))+[hi]))
        samples.extend((f'{j}_{q:g}',{j:float(q)}) for q in values)
    samples.extend([('full_fist',dict(zip(joints,[0,90,110,80]))),
                    ('precision_pinch',dict(zip(joints,[0,40,60,30]))),
                    ('spread_flex',dict(zip(joints,[15,90,110,80])))])
    rows=[];failures=[]
    for label,pose in samples:
        print('checking',label,flush=True)
        routes=middle_finger_routes(pose);ms=[route_metrics(r) for r in routes];gap=999.;bad=[]
        for i,r in enumerate(routes):
            tree=cKDTree(ms[i]['points'])
            for j in range(i+1,len(routes)):
                sampled=float(tree.query(ms[j]['points'],workers=1)[0].min())
                lower=sampled-(ms[i]['spacing']+ms[j]['spacing'])/2-.9
                if lower<gap:gap=lower
                if lower<0:bad.append({'a':r['name'],'b':routes[j]['name'],'conservative_envelope_gap_mm':lower,'sampled_centerline_distance_mm':sampled})
        radius=min(m['minimum_bend_radius_mm'] for m in ms)
        join=max(m['maximum_join_gap_mm'] for m in ms);tangent=max(m['maximum_tangent_error'] for m in ms)
        row={'pose':label,'angles':pose,'minimum_radius_mm':radius,'maximum_join_gap_mm':join,
             'maximum_tangent_error':tangent,'minimum_all_paths_0_45mm_envelope_gap_lower_bound_mm':gap}
        rows.append(row)
        if radius<3.5-1e-8 or join>1e-8 or tangent>1e-8 or bad:failures.append({**row,'overlap_candidates':bad})
    base=[route_metrics(r)['length_mm'] for r in middle_finger_routes()]
    matrix=[]
    epsilon=1e-4
    for j in joints:
        varied=[route_metrics(r)['length_mm'] for r in middle_finger_routes({j:epsilon})]
        matrix.append({'joint':j,'d_length_d_radian':[(v-b)/np.radians(epsilon) for v,b in zip(varied,base)]})
    report={'pose_count':len(rows),'rows':rows,'failures':failures,'length_jacobian_columns':matrix,
            'limitations':'All paths conservatively use0.45 radius in pairclearance; negativecandidate needs actualgroup radii/solids. Excludes hand solids.'}
    Path(__file__).with_name('middle_motion_routes_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pose_count':len(rows),'failures':failures,'length_jacobian_columns':matrix},indent=2))
    if failures:raise SystemExit(1)
