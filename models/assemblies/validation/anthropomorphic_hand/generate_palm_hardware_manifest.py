from pathlib import Path
import hashlib,json,sys
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.palm_hardware import palm_hardware_bodies
base=Path('models/assemblies');p=base/'STEP/anthropomorphic_hand/palm_hardware_review.step'
rows=[{'name':s.label,'frame':fr,'system':sy,'kind':k,'neutral_placement':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]} for s,fr,sy,k in palm_hardware_bodies()]
d={'step':'models/assemblies/STEP/anthropomorphic_hand/palm_hardware_review.step','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'body_count':len(rows),'coordinate_contract':'Every native body is already placed in assembled neutral world coordinates. Apply only the wrist_flexion frame delta for motion.','bodies':rows}
(base/'validation/anthropomorphic_hand/palm_hardware_placements.json').write_text(json.dumps(d,indent=2));print(d['sha256'],len(rows))
