"""Final29 wrist-guide occurrences against all15 accepted palm hardware."""
from pathlib import Path
import sys,json,hashlib
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.native_integration import overlay,ROOT
from check_assembly_interference import audit
bodies=[];evidence={}
for file in ['palm_hardware_placements.json','wrist_guide_frames.json']:
    manifest=json.loads((HERE/file).read_text())
    source=ROOT/'STEP/anthropomorphic_hand'/Path(manifest['step']).name
    bodies=overlay(bodies,source,manifest['bodies'],manifest['sha256'])
    evidence[str(source)]=manifest['sha256']
result=audit(bodies,HERE/'final_wrist_palm_hardware_interference.json')
result['input_sha256']=evidence
(HERE/'final_wrist_palm_hardware_interference.json').write_text(json.dumps(result,indent=2)+'\n')
assert result['pass']
