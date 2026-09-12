from lib.phalanx import make_phalanx
from cadgen import build123d as bd
s=make_phalanx(17,12,True)
for y in (10,12.07,14,15,16):
 a=s & (bd.Pos(5.275,y,0)*bd.Box(1.2,.01,20))
 print(y,[(p.bounding_box().min.Z,p.bounding_box().max.Z,p.volume) for p in a.solids()],flush=True)
