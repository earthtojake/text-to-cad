"""Native dorsal-nail geometry and all 75 within-system rigid contacts."""
import hashlib,itertools,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step
from OCP.BRepCheck import BRepCheck_Shell,BRepCheck_NoError
from lib.native_integration import leaves
from lib.phalanx_r5_boolean import common,cut
from check_native_reported_contacts import native_shapes
from check_pad_export_roundtrip import volume

def main():
    step=HERE.parents[1]/'STEP/anthropomorphic_hand/fingernail_export_repair_review.step'
    meta=HERE/'fingernail_export_repair_frames.json';mapping=json.loads(meta.read_text())
    native=native_shapes(step);authored={s.label:s for s in leaves(read_step(step))}
    assert len(native)==30 and set(native)==set(authored)=={r['name'] for r in mapping}
    report={'pass':False,'scope':__doc__,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (step,meta,Path(__file__),HERE.parents[1]/'src/anthropomorphic_hand/lib/fingernail.py')},'bodies':[],'pairs':[]}
    out=HERE/'fingernail_export_roundtrip.json'
    for name,s in native.items():
        a=authored[name];av,_=volume(a);nv,_=volume(s);relative=abs(av-nv)/av
        row={'name':name,'native_volume_mm3':nv,'authored_volume_mm3':av,'roundtrip_volume_relative_difference':relative,'valid_single_closed_solid':s.is_valid and len(s.solids())==1 and len(s.shells())==1 and all(BRepCheck_Shell(sh.wrapped).Closed()==BRepCheck_NoError for sh in s.shells()) and nv>0}
        equal=relative<1e-6
        if not equal:
            ab=cut(a,s);ba=cut(s,a);row['symmetric_difference_face_counts']=[len(ab.faces()),len(ba.faces())];equal=not ab.faces() and not ba.faces()
        row['roundtrip_geometry_equal']=equal;row['pass']=equal and row['valid_single_closed_solid']
        if name.endswith('dorsal_fingernail'):
            box=s.bounding_box();row['z_bounds_mm']=[box.min.Z,box.max.Z];row['pass'] &= abs(box.min.Z+4.72)<1e-5 and abs(box.max.Z+3.36)<1e-5
        report['bodies'].append(row);print('BODY',name,row['pass'],flush=True)
    for system in ('index','middle','ring','little','thumb'):
        parts=[s for n,s in native.items() if n.startswith(system+'_')]
        assert len(parts)==6
        for a,b in itertools.combinations(parts,2):
            v=volume(common(a,b))[0];report['pairs'].append(dict(a=a.label,b=b.label,intersection_mm3=v,pass_=v<1e-7))
        out.write_text(json.dumps(report,indent=2)+'\n');print('SYSTEM',system,flush=True)
    report['pass']=all(r['pass'] for r in report['bodies']) and all(r['pass_'] for r in report['pairs'])
    out.write_text(json.dumps(report,indent=2)+'\n');print('RESULT',report['pass'],flush=True)
    assert report['pass']

if __name__=='__main__':main()
