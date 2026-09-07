import sys
from pathlib import Path
from cadgen import read_step,build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
sys.path.insert(0,str(Path(__file__).parent))
from check_guide_mount_mutual import leaves
p=next(p for p in leaves(read_step(sys.argv[1])) if p.label==sys.argv[2]);c=BRepAlgoAPI_Check(p.wrapped,True,True);c.Perform();print('valid',c.IsValid(),flush=True)
for r in c.Result():
 print(r.GetCheckStatus(),flush=True)
 for n in ('GetFaultyShapes1','GetFaultyShapes2'):
  for s in getattr(r,n)():
   if not s.IsNull():print(n,s.ShapeType(),bd.Part(s).bounding_box(),flush=True)
