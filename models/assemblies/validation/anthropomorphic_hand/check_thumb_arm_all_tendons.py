"""All48 actual payout routes against the R2 native thumb arm at225 poses."""
import gzip,json,multiprocessing,sys
from pathlib import Path
from check_native_reported_contacts import native_shapes,sha,HERE
from check_full_route_bodies import audit
from lib.assembly import Body
from lib.layout import TENDONS
BODIES=MANIFEST=INPUTS=None
PREFIX='thumb_arm_r2_all_tendons'
def partition(index):
    names={t['name'] for i,t in enumerate(TENDONS) if i%8==index};rows=[];cache={}
    log=HERE.parents[3]/f'tmp/anthropomorphic_hand/{PREFIX}_{index}.log'
    with log.open('w',buffering=1) as stream:
        sys.stdout=stream;sys.stderr=stream
        for sample in MANIFEST['rows']:
            path=Path(sample['file']);assert sha(path)==sample['file_sha256'];packet=json.loads(gzip.decompress(path.read_bytes()))
            assert packet['source_sha256']==sample['source_sha256'] and packet['pose']==sample['pose']
            routes=[r for r in packet['routes'] if r['name'] in names];assert len(routes)==6
            r=audit(routes,BODIES,sample['pose'],cache=cache);r.update(sample=sample['label']);rows.append(r)
            (HERE/f'{PREFIX}_partition_{index}.json').write_text(json.dumps(dict(rows=rows,complete=len(rows)==225),indent=2)+'\n')
            print('ARM TENDONS',len(rows),sample['label'],r['pass'],flush=True)
    return rows
def main():
    global BODIES,MANIFEST,INPUTS
    path=HERE.parents[1]/'STEP/anthropomorphic_hand/thumb_reaction_arm_clearance_r2.step';name='thumb_cmc_negative_yaw_outlet_structural_jaw_1'
    shape=native_shapes(path)[name];assert len(shape.solids())==1;solid=shape.solids()[0];solid.label=name
    BODIES=[Body(solid,'thumb_cmc_abduction','thumb','guide_mount')]
    manifest_path=HERE/'payout_static_route_packet_manifest.json';MANIFEST=json.loads(manifest_path.read_text());assert MANIFEST['complete'] and len(MANIFEST['rows'])==225
    lib=HERE.parents[1]/'src/anthropomorphic_hand/lib'
    files=[Path(__file__),path,manifest_path,HERE/'check_native_reported_contacts.py',HERE/'check_full_route_bodies.py',HERE/'path_solid_clearance.py',HERE/'check_hand_route_pairs.py',HERE/'check_middle_hardware_paths.py',*[lib/n for n in ['assembly.py','layout.py','finger_routing.py','transport_guide.py','path_analysis.py']]]
    INPUTS={str(p):sha(p) for p in files}
    with multiprocessing.get_context('fork').Pool(2) as pool:parts=pool.map(partition,range(8))
    rows=[]
    for i,sample in enumerate(MANIFEST['rows']):
        items=[p[i] for p in parts];table=[r for item in items for r in item['tendon_table']];assert len(table)==48
        collisions=[r for item in items for r in item['collisions']]
        rows.append(dict(sample=sample['label'],pose=sample['pose'],tendon_table=table,collisions=collisions,pass_=not collisions))
    changed=[p for p,h in INPUTS.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=INPUTS,rows=rows,body=name,sample_count=225,tendon_count=48,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in rows));report['pass']=report.pop('pass_')
    (HERE/f'{PREFIX}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
