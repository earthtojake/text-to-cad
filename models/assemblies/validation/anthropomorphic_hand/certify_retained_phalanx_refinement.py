"""Certify four retained reductions against the frozen native baseline volumes."""
import ast,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from cadgen import build123d as bd
from cadgen.store.objects import object_path
from cadgen._internal.component_package import _build123d_shape_from_brep_bytes
from phalanx_beauty_review import REFINED
legacy=[]
for line in (ROOT/'tmp/anthropomorphic_hand/phalanx_beauty_subset.log').read_text().splitlines():
    try:r=json.loads(line)
    except ValueError:continue
    if r['name'] in REFINED:legacy.append(r)
assert {r['name'] for r in legacy}==REFINED
record=json.loads((ROOT/'tmp/anthropomorphic_hand/progress_viewer_store.json').read_text())
rows=[]
for r in legacy:
    o=next(o for o in record['occurrences'] if o['name']==r['name'])
    c=record['components'][o['component']]
    old=_build123d_shape_from_brep_bytes(object_path(c['brepObject']).read_bytes())
    native=ROOT/'models/assemblies/STEP/anthropomorphic_hand/phalanx_beauty_native'/(r['name']+'.step')
    new=bd.import_step(str(native))
    error=abs(old.volume-new.volume-r['removed_mm3'])
    r.update(baseline_brep_object=c['brepObject'],baseline_volume_mm3=old.volume,native_volume_mm3=new.volume,volume_conservation_error_mm3=error,native_sha256=hashlib.sha256(native.read_bytes()).hexdigest())
    r['pass']=r['subset_pass'] and error<1e-5 and new.is_valid and len(new.solids())==1
    rows.append(r);print(r,flush=True)
report={'pass':all(r['pass'] for r in rows),'refined_count':4,'unchanged_native_count':11,'rows':rows,'source_sha256':hashlib.sha256((SRC/'lib/phalanx.py').read_bytes()).hexdigest(),'baseline_source_sha256':hashlib.sha256((HERE/'phalanx_pre_beauty_baseline.py').read_bytes()).hexdigest(),'proof':'Zero new-minus-old volume from independently constructed baseline/candidate bodies, plus independent cached native baseline versus exported candidate volume conservation. Eleven other actual native bodies are imported unchanged from the frozen integration base. Strict every-placement validation is separate.'}
(HERE/'phalanx_beauty_retained_certificate.json').write_text(json.dumps(report,indent=2)+'\n')
if not report['pass']:raise SystemExit(1)
