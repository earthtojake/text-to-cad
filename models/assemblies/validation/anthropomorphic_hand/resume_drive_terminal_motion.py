"""Finish the one unfinished native terminal sweep, retaining47 completed rows."""
import json,hashlib,time
from pathlib import Path
import drive_terminal_motion_check as check
from cadgen import read_step
from lib.layout import JOINTS
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from types import SimpleNamespace
HERE=Path(__file__).parent
STEP=check.ROOT/'models/assemblies/STEP/anthropomorphic_hand'
def box(shape):
 b=Bnd_Box();BRepBndLib.Add_s(shape.wrapped,b,False);v=b.Get()
 return SimpleNamespace(min=SimpleNamespace(**dict(zip('XYZ',v[:3]))),max=SimpleNamespace(**dict(zip('XYZ',v[3:]))))
cache={}
def vol(a,b):
 def bounds(s):
  k=id(s)
  if k not in cache:cache[k]=(s,box(s))
  return cache[k][1]
 x,y=bounds(a),bounds(b)
 if any(getattr(x.max,k)<getattr(y.min,k)-1e-7 or getattr(y.max,k)<getattr(x.min,k)-1e-7 for k in 'XYZ'):return 0.
 c=a&b;return c.volume if c is not None else 0.
check.vol=vol
leaves=lambda n:[s for c in n.children for s in leaves(c)] if n.children else [n]
report=json.loads((HERE/'drive_terminal_motion_check.json').read_text());assert len(report['completed_routes'])==47
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={p.name:sha(p) for p in [STEP/'drive_terminal_placements.step',STEP/'joint_hardware_review.step']}
byname={p.label:p for p in leaves(read_step(STEP/'drive_terminal_placements.step'))};assert len(byname)==336
hardware=[]
for h in leaves(read_step(STEP/'joint_hardware_review.step')):
 j=next(j for j in JOINTS if h.label.startswith(j.name+'_'))
 hardware.append((h,j.parent if h.label.endswith('_bushing') else j.name,box(h)))
rows=check.terminal_placements();check._CONTEXT=(rows,byname,hardware)
for i,row in enumerate(rows):
 if row['name'] in report['completed_routes']:continue
 print('Completing',row['name'],flush=True);r=check.check_route(i)
 report['completed_routes'].append(r['name'])
 for k in ['motion_seating','hardware_motion','failures']:report[k].extend(r[k])
assert len(report['completed_routes'])==48
assert all(sha(STEP/n)==v for n,v in inputs.items())
report.update(partial=False,ok=not report['failures'],resume_inputs_sha256=inputs)
(HERE/'drive_terminal_motion_check.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS' if report['ok'] else report['failures'],flush=True)
