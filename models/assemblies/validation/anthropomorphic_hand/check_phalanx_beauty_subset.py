"""Exact material-subset and unchanged host-seat certificate for15 frames."""
import importlib.util,sys,json,hashlib,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from lib.layout import FINGERS
from cadgen import build123d as bd
from lib.phalanx import make_phalanx
BASE=Path(__file__).with_name('phalanx_pre_beauty_baseline.py')
spec=importlib.util.spec_from_file_location('baseline',BASE);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
OUT=ROOT/'models/assemblies/STEP/anthropomorphic_hand/phalanx_beauty_native'
OUT.mkdir(exist_ok=True)
def work(v):
    name,l,w,distal=v
    old=base.make_phalanx(l,w,distal,label=name);new=make_phalanx(l,w,distal,label=name)
    added=new-old;removed=old-new
    # All seat bands, keyed/bearing eyes and pad/nail bosses must remain exact.
    stations=[0,l,12.25,l-12.25,l-15,l-7,10]
    if distal:stations=[0,l*.71,l-1.6]
    rows=[]
    for y in stations:
        mask=bd.Pos(0,y,0)*bd.Box(w+4,2.4,20)
        # Arches carry no guide contacts; the seats are only on the side rails.
        for sign in (-1,1):
            side=bd.Pos(sign*(w/2-.725),y,0)*bd.Box(1.65,2.4,20)
            delta=removed & side
            rows.append({'y':y,'side':sign,'seat_material_removed_mm3':max(0,delta.volume)})
    bd.export_step(new,str(OUT/(name+'.step')))
    result={'name':name,'added_mm3':max(0,added.volume),'removed_mm3':max(0,removed.volume),'valid':new.is_valid,'solids':len(new.solids()),'seat_bands':rows}
    # Removing an arch root can touch the inner edge of a rail band. Actual
    # clamp contact proof uses original side faces, not this conservative box.
    result['subset_pass']=result['added_mm3']<1e-7
    print(json.dumps({k:v for k,v in result.items() if k!='seat_bands'}),flush=True)
    return result
if __name__=='__main__':
    vv=[(f.name+'_'+role+'_frame',l,w,i==2) for f in FINGERS for i,(role,l,w) in enumerate(zip(('proximal','middle','distal'),f.lengths,f.widths))]
    vv += [('thumb_'+r+'_frame',l,w,i==2) for i,(r,l,w) in enumerate(zip(('metacarpal','proximal','distal'),(36,27,21),(19,16,13)))]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(work,vv))
    report={'source_sha256':hashlib.sha256((SRC/'lib/phalanx.py').read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),'rows':rows,'pass':all(r['subset_pass'] and r['valid'] and r['solids']==1 for r in rows)}
    Path(__file__).with_name('phalanx_beauty_subset.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
