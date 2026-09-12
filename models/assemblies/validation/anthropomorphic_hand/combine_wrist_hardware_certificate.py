"""Combine direct ROM checks with byte-identical native-body inheritance."""
import json,hashlib
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parents[1]
changed=json.loads((HERE/'wrist_guide_hardware_rom_changed_all.json').read_text())
assert changed['poses']==65 and changed['pass'], 'Changed-body grid incomplete or failed'
unchanged={p['name'] for p in changed['unchanged_native_bodies']}
assert len(unchanged)+changed['guide_count']==29
source=json.loads((HERE/'wrist_hardware_audit_sources.json').read_text())
for path,digest in source.items():
 if Path(path).name!='wrist_guide_mounts_review.step':assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,(path,'hardware changed')
old_digest=hashlib.sha256((ROOT/'STEP/anthropomorphic_hand/imported/wrist_guide_pre_mirror.step').read_bytes()).hexdigest()
new_digest=hashlib.sha256((ROOT/'STEP/anthropomorphic_hand/wrist_guide_mounts_review.step').read_bytes()).hexdigest()
assert new_digest==changed['guide_step_sha256']
base={}
for yaw in (-20,-10,0,10,20):
 d=json.loads((HERE/f'wrist_guide_hardware_rom_{yaw}.json').read_text())
 assert d['poses']==13 and d['guide_step_sha256']==old_digest
 for row in d['rows']:
  key=tuple(sorted(row['pose'].items()));assert key not in base;base[key]=row
assert len(base)==65
rows=[]
for row in changed['rows']:
 old=base[tuple(sorted(row['pose'].items()))]
 inherited=[p for p in old['interferences'] if p['guide'] in unchanged]
 rows.append({'pose':row['pose'],'unchanged_body_interferences':inherited,'changed_body_interferences':row['interferences']})
result={'pass':all(not r['unchanged_body_interferences'] and not r['changed_body_interferences'] for r in rows),'guide_count':29,'poses':65,'guide_step_sha256':new_digest,'baseline_step_sha256':old_digest,'directly_rechecked_body_count':changed['guide_count'],'byte_identical_native_bodies':changed['unchanged_native_bodies'],'hardware_source_sha256':{k:v for k,v in source.items() if Path(k).name!='wrist_guide_mounts_review.step'},'native_envelope_containment_report':'wrist_hardware_envelope_containment.json','rows':rows}
(HERE/'wrist_final_hardware_rom.json').write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k not in ('rows','byte_identical_native_bodies','hardware_source_sha256')});assert result['pass']
