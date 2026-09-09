"""One shared solve per pose: full paths, mutual envelopes, and actual hardware."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import check_middle_hardware_paths as hardware
from check_middle_routes import route_metrics
from lib.finger_routing import finger_routes
from lib.layout import JOINT_BY_NAME

if __name__=='__main__':
    finger_name=sys.argv[sys.argv.index('--finger')+1] if '--finger' in sys.argv else 'middle'
    joints=[finger_name+'_'+j for j in ('mcp_abduction','mcp_flexion','pip','dip')]
    samples=[('flat_open',{})]
    for j in joints:
        lo,hi=JOINT_BY_NAME[j].limits
        samples.extend((f'{j}_{q:g}',{j:float(q)}) for q in sorted(set(list(np.arange(lo,hi+1e-8,10))+[hi])))
    samples.extend([('full_fist',dict(zip(joints,[0,90,110,80]))),('precision_pinch',dict(zip(joints,[0,40,60,30]))),('spread_flex',dict(zip(joints,[JOINT_BY_NAME[joints[0]].limits[1],90,110,80])))])
    neutral_fan={'index':20.,'middle':5.,'ring':-5.,'little':-25.}
    samples.append(('adducted_full_fist',dict(zip(joints,[-neutral_fan[finger_name],90,110,80]))))
    if '--compound-only' in sys.argv:
        samples=[sample for sample in samples if sample[0]=='adducted_full_fist']
    prototypes=hardware.hardware(include_carrier="--without-carrier" not in sys.argv,finger_name=finger_name)
    if '--without-carrier' in sys.argv:prototypes=[p for p in prototypes if p[0]!='mcp_carrier']
    roots=Path('models/assemblies/src/anthropomorphic_hand/lib')
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [roots/n for n in ('finger_routing.py','bowden_mcp.py','yaw_transport.py','pip_transport.py','phalanx.py','pulley.py','universal_carrier.py','layout.py')]}
    report={'scope':[p[0] for p in prototypes],'source_sha256':source_hashes,'rows':[],'pass':False}
    output=Path(__file__).with_name(finger_name+('_adducted_fist_report.json' if '--compound-only' in sys.argv else '_combined_report.json'))
    for label,pose in samples:
        print('checking',label,flush=True)
        rs=finger_routes(finger_name,pose);ms=[route_metrics(r) for r in rs]
        conflicts=[];minimum_gap=999.
        for i in range(len(rs)):
            tree=cKDTree(ms[i]['points'])
            for j in range(i+1,len(rs)):
                gap=float(tree.query(ms[j]['points'],workers=1)[0].min())-(ms[i]['spacing']+ms[j]['spacing'])/2-.9
                minimum_gap=min(minimum_gap,gap)
                if gap<0:conflicts.append({'a':rs[i]['name'],'b':rs[j]['name'],'gap_lower_bound_mm':gap})
        row={'label':label,'pose':pose,'minimum_radius_mm':min(m['minimum_bend_radius_mm'] for m in ms),'maximum_join_gap_mm':max(m['maximum_join_gap_mm'] for m in ms),'maximum_tangent_error':max(m['maximum_tangent_error'] for m in ms),'minimum_mutual_gap_lower_bound_mm':minimum_gap,'mutual_conflicts':conflicts,'hardware':hardware.check(pose,prototypes,finger_name=finger_name)}
        row['pass']=not conflicts and not row['hardware']['collisions'] and row['minimum_radius_mm']>=3.5-1e-8 and row['maximum_join_gap_mm']<1e-8 and row['maximum_tangent_error']<1e-8
        report['rows'].append(row);output.write_text(json.dumps(report,indent=2)+'\n')
        print(label,'PASS' if row['pass'] else json.dumps(row),flush=True)
    report['pass']=all(r['pass'] for r in report['rows']);output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
