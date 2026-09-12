"""Continuity, curvature and all tendon spacing with physical actuator payout."""
import argparse,gzip,hashlib,json,multiprocessing,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;LIB=HERE.parents[1]/'src/anthropomorphic_hand/lib'
sys.path.insert(0,str(LIB.parent))
from check_static_route_packets import audit,DATA
from check_tendon_self_spacing import check_route
MANIFEST=INPUTS=None;PREFIX='payout_static_curves'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def partition(index):
    selected=MANIFEST['rows'][index::4];rows=[];cache={}
    out=HERE/f'{PREFIX}_partition_{index}.json'
    if out.exists():
        old=json.loads(out.read_text())
        if old['input_sha256']==INPUTS:rows=old['rows']
    for i,r in enumerate(rows):assert (r['sample'],r['pose'])==(selected[i]['label'],selected[i]['pose'])
    for sample in selected[len(rows):]:
        path=Path(sample['file']);assert sha(path)==sample['file_sha256']
        packet=json.loads(gzip.decompress(path.read_bytes()));assert packet['pose']==sample['pose'] and packet['source_sha256']==sample['source_sha256']
        curves=audit(packet['routes']);spacing=[]
        for route in packet['routes']:
            key=hashlib.sha256(json.dumps(route['groups'],sort_keys=True).encode()).hexdigest()
            if key not in cache:cache[key]=check_route(route)
            spacing.append(cache[key])
        row=dict(sample=sample['label'],pose=sample['pose'],curve_gate=curves,self_spacing=spacing,pass_=curves['pass'] and all(r['pass'] for r in spacing));rows.append(row)
        out.write_text(json.dumps(dict(input_sha256=INPUTS,rows=rows,complete=len(rows)==len(selected)),indent=2)+'\n')
        print('PAYOUT CURVES',index,len(rows),sample['label'],row['pass_'],'bad radii',[(r['tendon'],r['minimum_radius_mm']) for r in curves['tendon_table'] if not r['clear']],'conflicts',len(curves['conflicts']),flush=True)
        if len(DATA)>2000:DATA.clear()
    return rows

def main():
    global MANIFEST,INPUTS,PREFIX
    parser=argparse.ArgumentParser();parser.add_argument('--sample');parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    path=HERE/'payout_static_route_packet_manifest.json';MANIFEST=json.loads(path.read_text());assert MANIFEST['complete'] and len(MANIFEST['rows'])==225
    assert all(sha(p)==h for p,h in MANIFEST['input_sha256'].items())
    INPUTS={**MANIFEST['input_sha256'],**{str(p):sha(p) for p in (Path(__file__),path,HERE/'check_static_route_packets.py',HERE/'check_tendon_self_spacing.py',HERE/'check_hand_route_pairs.py',LIB/'path_analysis.py',LIB/'finger_routing.py')}}
    if args.sample:
        MANIFEST['rows']=[r for r in MANIFEST['rows'] if r['label']==args.sample];assert len(MANIFEST['rows'])==1
        PREFIX=f'payout_static_curves_probe_{args.sample}'
    with multiprocessing.get_context('fork').Pool(args.workers) as pool:parts=pool.map(partition,range(4))
    rows=[r for part in parts for r in part];assert len(rows)==len(MANIFEST['rows'])
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=INPUTS,rows=rows,sample_count=len(rows),full_static_coverage=len(rows)==225,complete=not changed,changed_during_audit=changed,pass_=not changed and all(r['pass_'] for r in rows));report['pass']=report.pop('pass_')
    (HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
