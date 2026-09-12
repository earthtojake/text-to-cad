"""Freeze the225 static hand poses with their physically solved actuator payout.

Hand and wrist path segments are inherited byte-for-byte from certified static
packets. Only stored rope, free lead and forearm exit change. No choreography
or explode timing is authored here.
"""
import copy,gzip,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from lib.actuator_payout import solve_rotation
from lib.forearm_routing import forearm_route
from lib.layout import TENDONS
from lib.path_analysis import path_length

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    manifest_path=HERE/'final_static_route_packet_manifest.json';manifest=json.loads(manifest_path.read_text())
    assert manifest['complete'] and len(manifest['rows'])==225
    inputs={str(p):sha(p) for p in [Path(__file__),manifest_path,*[SRC/'lib'/n for n in ('actuator_payout.py','forearm_routing.py','capstan_path.py','layout.py','path_analysis.py')]]}
    source=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    neutral_row=next(r for r in manifest['rows'] if not r['pose']);assert sha(neutral_row['file'])==neutral_row['file_sha256']
    neutral=json.loads(gzip.decompress(Path(neutral_row['file']).read_bytes()))
    base={r['name']:path_length(r['path']) for r in neutral['routes']}
    tendons={t['name']:t for t in TENDONS};cache={};rows=[];payout=[]
    directory=HERE/'payout_static_packets';directory.mkdir(exist_ok=True)
    for sample in manifest['rows']:
        path=Path(sample['file']);assert sha(path)==sample['file_sha256']
        packet=json.loads(gzip.decompress(path.read_bytes()));assert packet['source_sha256']==sample['source_sha256'] and packet['pose']==sample['pose']
        routes=[];angles={};lengths=[]
        for original in packet['routes']:
            name=original['name'];assert original['capstan_rotation']==0.
            change=path_length(original['path'])-base[name];key=(name,float(change).hex())
            if key not in cache:cache[key]=solve_rotation(name,change)
            q=cache[key];forearm=forearm_route(tendons[name],q)
            assert [g['label'] for g in original['groups'][:4]]==[g['label'] for g in forearm['groups']]
            route=copy.deepcopy(original);route['groups']=[*forearm['groups'],*route['groups'][4:]]
            route['path']=[segment for group in route['groups'] for segment in group['path']]
            route['capstan_rotation']=q;route['spool_termination']=forearm['inlet']
            residual=path_length(route['path'])-base[name];assert abs(residual)<1e-7,(sample['label'],name,residual)
            routes.append(route);angles[name]=q
            lengths.append(dict(tendon=name,capstan_rotation_rad=q,downstream_change_mm=change,total_length_residual_mm=residual,pass_=True))
        assert len(routes)==48 and set(angles)==set(tendons)
        result=dict(source_sha256=source,pose=sample['pose'],routes=routes,actuator_angles_rad=angles,parent_packet_sha256=sample['file_sha256'])
        data=json.dumps(result,separators=(',',':')).encode();identity=hashlib.sha256(data).hexdigest()
        out=directory/f'{sample["label"]}_{identity[:16]}.json.gz';out.write_bytes(gzip.compress(data,mtime=0))
        rows.append(dict(label=sample['label'],pose=sample['pose'],file=str(out),file_sha256=sha(out),source_sha256=source,tendon_count=48,parent_packet_sha256=sample['file_sha256']))
        payout.append(dict(sample=sample['label'],pose=sample['pose'],tendons=lengths,pass_=True))
        print('PAYOUT PACKET',len(rows),sample['label'],max(map(abs,angles.values())),flush=True)
    assert all(sha(p)==h for p,h in inputs.items())
    report=dict(scope=__doc__,input_sha256=inputs,source_sha256=source,rows=rows,sample_count=225,complete=True)
    (HERE/'payout_static_route_packet_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (HERE/'final_static_actuator_payout.json').write_text(json.dumps(dict(scope=__doc__,input_sha256={**inputs,str(HERE/'payout_static_route_packet_manifest.json'):sha(HERE/'payout_static_route_packet_manifest.json')},rows=payout,complete=True,pass_=True),indent=2)+'\n')
if __name__=='__main__':main()
