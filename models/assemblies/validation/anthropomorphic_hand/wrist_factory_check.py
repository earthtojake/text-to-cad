"""Fresh-process reproducibility check, independent of the CAD build daemon."""
import sys,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[4]
source=root/'models/assemblies/src/anthropomorphic_hand'
sys.path.insert(0,str(source))
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle
rows=[]
for factory in (make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle):
    s=factory()
    row={'factory':factory.__name__,'volume_mm3':s.volume,'solid_count':len(s.solids()),'valid':s.is_valid}
    print(json.dumps(row),flush=True);rows.append(row)
    assert row['valid'] and row['solid_count']==1
Path(__file__).with_suffix('.json').write_text(json.dumps({'source_sha256':hashlib.sha256((source/'lib/wrist.py').read_bytes()).hexdigest(),'parts':rows},indent=2))
