"""Compact fixed CMC seat and hardware versus the actual moving native links."""
import sys,json,hashlib
from pathlib import Path
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.native_integration import frozen_bodies,overlay,ROOT
from lib.assembly import Body,posed_bodies,joint_location
from lib.layout import JOINT_BY_NAME
from check_assembly_interference import audit
bodies=[b for b in frozen_bodies(False) if b.name in ('thumb_cmc_carrier','thumb_metacarpal_frame')]
assert len(bodies)==2
item=json.loads((HERE/'positive_yaw_hardware_build_handoff.json').read_text())['compact_cmc_yaw']
bodies=overlay(bodies,Path(item['step']),json.loads(Path(item['frames']).read_text()),item['sha256'])
seat=joint_location(JOINT_BY_NAME['thumb_cmc_abduction'])*bd.Pos(0,0,9.3)*(bd.Cylinder(1.85,1.4)-bd.Cylinder(1.58,3.4))
seat.label='compact_CMC_protected_palm_seat';bodies.append(Body(seat,'wrist_flexion','palm','seat'))
manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());rows=[];cache={}
for sample in manifest['rows']:
    result=audit(posed_bodies(bodies,sample['pose']),HERE/'compact_cmc_context_live.json',cache)
    result['sample']=sample['label'];result['pose']=sample['pose'];rows.append(result)
    report={'body_count':len(bodies),'sample_count':len(rows),'rows':rows,'pass':len(rows)==225 and all(r['pass'] for r in rows)}
    (HERE/'compact_cmc_context_gate.json').write_text(json.dumps(report,indent=2)+'\n')
assert report['pass']
