"""All48 accepted full routes against the fixed middle palm reaction bank."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd,read_step
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.transport_guide import path_wire
from check_middle_hardware_paths import bbox_gap
from check_guide_combs import common_volume

if __name__=='__main__':
 root=Path(__file__).resolve().parents[2]
 def leaves(shape):
  if shape.children:
   return [p for child in shape.children for p in leaves(child)]
  return [shape]
 if '--all-banks' in sys.argv:
  assembly=read_step(root/'STEP/anthropomorphic_hand/palm_guide_mounts_review.step')
  host=next(p for p in read_step(root/'STEP/anthropomorphic_hand/palm_frame_review.step').children if p.label=='palm_metacarpal_truss')
  parts=leaves(assembly)
 else:
  assembly=read_step(root/'STEP/anthropomorphic_hand/palm_guide_bank_review.step')
  host=next(p for p in assembly.children if p.label=='palm_metacarpal_truss')
  parts=[p for p in assembly.children if p.label!='palm_metacarpal_truss']
 bounds={p.label:p.bounding_box(optimal=False) for p in parts}
 report={'scope':'all48 full neutral routes; actual palm frame; mutual mount solids','collisions':[],'host_interferences':[],'mutual_interferences':[],'tested':0}
 for route in ([] if "--body-only" in sys.argv else NEUTRAL_ROUTES):
  for g in route['groups']:
   radius=.45 if g['guide'] in ('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .30
   wire=path_wire(g['path']);box=wire.bounding_box(optimal=False)
   for p in parts:
    if bbox_gap(box,bounds[p.label])>radius+.05:continue
    distance=wire.distance_to(p);report['tested']+=1
    if distance<radius-1e-6:report['collisions'].append({'route':route['name'],'group':g['label'],'part':p.label,'distance':distance,'radius':radius})
  print(route['name'],len(report['collisions']),flush=True)
 for i,p in enumerate(parts):
  if bbox_gap(bounds[p.label],host.bounding_box(optimal=False))<.005:
   volume=common_volume(p,host)
   if volume>1e-7:report['host_interferences'].append({'part':p.label,'volume':volume})
  for q in parts[i+1:]:
   if bbox_gap(bounds[p.label],bounds[q.label])>.005:continue
   volume=common_volume(p,q)
   if volume>1e-7:report['mutual_interferences'].append({'a':p.label,'b':q.label,'volume':volume})
 report['pass']=not any(report[k] for k in ('collisions','host_interferences','mutual_interferences'))
 Path(__file__).with_name('palm_guide_banks_body_report.json' if '--body-only' in sys.argv else 'palm_guide_banks_report.json' if '--all-banks' in sys.argv else 'palm_guide_bank_report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report),flush=True)
 if not report['pass']:raise SystemExit(1)
