from cadgen import build123d as bd,read_step
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
path='models/assemblies/STEP/anthropomorphic_hand/phalanx_continuous_r5.step'
for name,loader in [('read_step',read_step),('native_STEP_import',bd.import_step)]:
 h=loader(path);c=bd.Pos(9,38,3.5)*bd.Box(18,.02,6.9)
 r=bd.Compound(BRepAlgoAPI_Common(h.wrapped,c.wrapped).Shape())
 print({'loader':name,'contains_positive_rail':h.is_inside((8.275,38,3.5)),'common_solids':len(r.solids()),'common_bbox':str(r.bounding_box())},flush=True)
