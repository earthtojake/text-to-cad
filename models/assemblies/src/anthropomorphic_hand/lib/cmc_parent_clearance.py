"""Machined clearances for the recorded wrist motion next to the CMC bank."""
import json
from pathlib import Path
from cadgen import build123d as bd
from lib.guide_mounts import _finish
from lib.transport_guide import path_wire
DATA=json.loads(Path(__file__).with_name('cmc_parent_reliefs.json').read_text())
def clear_cmc_part(part):
 entries=DATA.get(part.label,[])
 if not entries:return [part]
 tools=[]
 for e in entries:
  wire=path_wire([e['segment']]);tools.append(bd.sweep(bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(e['radius']),path=wire))
 cut=part.cut(*tools)
 if cut is None or not len(cut.solids()):raise ValueError(part.label+': clearance removed whole component')
 return [_finish(s,part.label+('_'+str(i+1) if len(cut.solids())>1 else '')) for i,s in enumerate(cut.solids())]
