import json,time,hashlib
from pathlib import Path
from cadgen import build123d as bd,read_step
from cadgen.validity import check_occurrence_shape
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
p=Path('models/assemblies/STEP/anthropomorphic_hand/phalanx_continuous_r5.step');out=Path('models/assemblies/validation/anthropomorphic_hand/rail_loader_comparison_r5.json')
r={'step_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'complete':False,'rows':[]}
for name,loader in [('read_step',read_step),('native_STEP_import',bd.import_step)]:
 h=loader(p);box=h.bounding_box();c=bd.Pos(9,38,3.5)*bd.Box(18,.02,6.9);com=bd.Compound(BRepAlgoAPI_Common(h.wrapped,c.wrapped).Shape())
 row={'loader':name,'volume':h.volume,'bounds':{'min':tuple(box.min),'max':tuple(box.max)},'solids':len(h.solids()),'faces':len(h.faces()),'edges':len(h.edges()),'topology_valid':h.is_valid,'contains_positive_rail':h.is_inside((8.275,38,3.5)),'section_common_solids':len(com.solids())}
 r['rows'].append(row);out.write_text(json.dumps(r,indent=2));print(row,flush=True)
 row['strict']=check_occurrence_shape(h.wrapped);out.write_text(json.dumps(r,indent=2));print('strict',name,row['strict'],flush=True)
r['complete']=True;out.write_text(json.dumps(r,indent=2))
