from cadgen import build123d as bd
from cadgen.validity import check_occurrence_shape
from lib.layout import THUMB_CMC
for rot in (0,-90,90,45):
 s=bd.Rot(90,0,0)*bd.Rot(0,0,rot)*bd.Sphere(1)
 s=s.transform_geometry(bd.Matrix([[4.81,0,0,0],[0,5.67,0,0],[0,0,.68,0],[0,0,0,1]]))
 s=bd.Pos(0,15.71,-4.04)*s
 p=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,63,0)*s
 print(rot,check_occurrence_shape(p.wrapped),flush=True)
