"""Small exact machined cap passages from recorded guide sweeps."""
import json
from pathlib import Path
from cadgen import build123d as bd
from lib.guide_mounts import _finish
from lib.transport_guide import path_wire
DATA=json.loads(Path(__file__).with_name('remaining_cap_reliefs.json').read_text())

def clear_cap(part):
 tools=[]
 if part.label=='thumb_cmc_yaw_drive_-1_host_cap':
  tools.append(bd.Pos(-28.8440348,40.1746561,-17.88592455)*bd.Sphere(.05))
 entries=DATA.get(part.label,[])
 for name,rows in DATA.items():
  if name.endswith('structural') and part.label.startswith(name+'_'):entries=[*entries,*rows]
 for entry in entries:
  wire=path_wire([entry['segment']]);tools.append(bd.sweep(bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(entry['radius']),path=wire))
 if not tools:return [part]
 cut=part.cut(*tools)
 if cut is None or not len(cut.solids()):raise ValueError(part.label+': cap passage removed whole component')
 return [_finish(s,part.label+('_'+str(i+1) if len(cut.solids())>1 else '')) for i,s in enumerate(cut.solids())]
