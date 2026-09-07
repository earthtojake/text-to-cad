"""Conservative native B-rep face bounds followed by containment witnesses."""
import numpy as np
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_IN,TopAbs_ON
from OCP.gp import gp_Pnt
class NativeFaceBounds:
 def __init__(self,p):
  self.boxes=[]
  for f in p.faces():
   b=f.bounding_box();self.boxes.append([[x,y,z,1] for x in(b.min.X,b.max.X) for y in(b.min.Y,b.max.Y) for z in(b.min.Z,b.max.Z)])
  self.boxes=np.array(self.boxes);self.lo=self.boxes[:,:,:3].min(1);self.hi=self.boxes[:,:,:3].max(1);self.point=np.array([*tuple(p.vertices()[0].center()),1]);self.solids=[BRepClass3d_SolidClassifier(s.wrapped) for s in p.solids()]
 def contains(self,p):
  for s in self.solids:
   s.Perform(gp_Pnt(*p[:3]),1e-7)
   if s.State() in(TopAbs_IN,TopAbs_ON):return True
  return False
 def disjoint(self,other,rel):
  moved=other.boxes@rel.T;lo=moved[:,:,:3].min(1);hi=moved[:,:,:3].max(1)
  gaps=np.maximum(0,np.maximum(self.lo[:,None,:]-hi[None,:,:],lo[None,:,:]-self.hi[:,None,:]))
  if np.any((gaps*gaps).sum(2)<1e-10):return False
  return not self.contains(rel@other.point) and not other.contains(np.linalg.inv(rel)@self.point)
