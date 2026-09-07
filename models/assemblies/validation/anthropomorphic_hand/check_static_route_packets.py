"""Continuous sample-envelope spacing, exact extrema and join gates for packets."""
import sys,json,gzip,hashlib,argparse,time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.path_analysis import sample_path,path_length,path_min_radius
from lib.finger_routing import endpoint,tangent
from check_hand_route_pairs import group_radius
root=Path(__file__).parent
DATA={};PAIRS={}
def data(group):
    key=hashlib.sha256(json.dumps(group['path'],sort_keys=True).encode()).digest()
    if key not in DATA:
        points=sample_path(group['path'],.025)
        DATA[key]={'points':points,'tree':cKDTree(points),'low':points.min(axis=0),'high':points.max(axis=0),'length':path_length(group['path']),'radius':path_min_radius(group['path'])}
    return key,DATA[key]
def audit(routes):
    entries=[];table=[]
    for route in routes:
        length=0.;minimum=float('inf')
        for group in route['groups']:
            key,d=data(group);length+=d['length'];minimum=min(minimum,d['radius']);entries.append((route['name'],group['label'],group_radius(group),key,d))
        path=route['path'];gap=max((float(np.linalg.norm(np.asarray(endpoint(a,True))-endpoint(b))) for a,b in zip(path,path[1:])),default=0.)
        terr=max((float(np.linalg.norm(np.asarray(tangent(a,True))-tangent(b))) for a,b in zip(path,path[1:])),default=0.)
        table.append({'tendon':route['name'],'length_mm':length,'minimum_radius_mm':minimum,'maximum_join_gap_mm':gap,'maximum_tangent_error':terr,'clear':minimum>=3.5-1e-10 and gap<1e-8 and terr<1e-8})
    conflicts=[];checks=0;reused=0;minimum=999.
    for i,(name,label,radius,key,d) in enumerate(entries):
        for name2,label2,radius2,key2,e in entries[i+1:]:
            if name==name2:continue
            bound=np.linalg.norm(np.maximum.reduce([d['low']-e['high'],e['low']-d['high'],np.zeros(3)]))
            if bound>radius+radius2+.1:continue
            pair=(key,key2,radius,radius2)
            if pair in PAIRS:gap=PAIRS[pair];reused+=1
            else:
                gap=float(d['tree'].query(e['points'],workers=1)[0].min())-.025-radius-radius2;PAIRS[pair]=gap;checks+=1
            minimum=min(minimum,gap)
            if gap<0:conflicts.append({'a':name,'group_a':label,'b':name2,'group_b':label2,'surface_gap_lower_bound_mm':gap})
    return {'tendon_table':table,'conflicts':conflicts,'minimum_checked_gap_mm':minimum,'new_exact_cloud_distance_pairs':checks,'identical_path_pair_proofs_reused':reused,'pass':not conflicts and all(r['clear'] for r in table)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--follow',action='store_true');args=parser.parse_args()
    rows=[];seen=set()
    while True:
        manifest=json.loads((root/'static_route_packet_manifest.json').read_text())
        for sample in manifest['rows']:
            if sample['label'] in seen:continue
            packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()))
            if packet['source_sha256']!=manifest['source_sha256']:raise ValueError('mixed source packet')
            result=audit(packet['routes']);result.update(sample=sample['label'],pose=sample['pose']);rows.append(result);seen.add(sample['label'])
            report={'sample_count':len(rows),'complete':manifest['complete'] and len(rows)==len(manifest['rows']),'pass':manifest['complete'] and len(rows)==len(manifest['rows']) and all(r['pass'] for r in rows),'source_sha256':manifest['source_sha256'],'rows':rows}
            (root/'static_full_tendon_curve_gate.json').write_text(json.dumps(report,indent=2)+'\n')
            print(sample['label'],result['pass'],'conflicts',len(result['conflicts']),'newpairs',result['new_exact_cloud_distance_pairs'],'reused',result['identical_path_pair_proofs_reused'],flush=True)
            for failure in result['conflicts']:print('CONFLICT',failure,flush=True)
        if manifest['complete'] or not args.follow:break
        time.sleep(5)
    if not report['pass']:raise SystemExit(1)
