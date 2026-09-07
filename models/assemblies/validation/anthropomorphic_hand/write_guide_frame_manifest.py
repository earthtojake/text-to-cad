import sys,json,hashlib
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
from cadgen import read_step
from check_guide_mount_mutual import leaves
from check_remaining_guide_routes import frame
name=sys.argv[1];file=ROOT/'STEP/anthropomorphic_hand'/sys.argv[2];parts=leaves(read_step(file));rows=[]
for p in parts:
 fr=frame(p.label);system='thumb' if p.label.startswith('thumb_') else 'little' if p.label.startswith('little_cup_child') else 'palm' if p.label.startswith(('little_cup_fixed','palm_cup')) else 'wrist'
 rows.append({'name':p.label,'frame':fr,'system':system,'kind':'fastener' if 'screw' in p.label else 'guide_mount'})
assert len({r['name'] for r in rows})==len(rows)
result={'step':str(file.resolve()),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'body_count':len(rows),'bodies':rows};(HERE/(name+'_frames.json')).write_text(json.dumps(result,indent=2)+'\n');print(result['body_count'],result['sha256'])
