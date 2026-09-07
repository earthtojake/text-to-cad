"""Positive native solid distance is a disjointness proof, never a collision waiver."""
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Cylinder,GeomAbs_Cone,GeomAbs_Sphere,GeomAbs_Torus

_QUALIFIED={}
def simple_analytic(shape):
    local=shape.Located(TopLoc_Location());bucket=_QUALIFIED.setdefault(hash(local),[])
    for saved,qualified in bucket:
        if saved.IsSame(local):return qualified
    explorer=TopExp_Explorer(local,TopAbs_FACE);count=0;qualified=True
    while explorer.More():
        count+=1
        surface=BRepAdaptor_Surface(TopoDS.Face_s(explorer.Current()))
        if count>16 or surface.GetType() not in (GeomAbs_Plane,GeomAbs_Cylinder,GeomAbs_Cone,GeomAbs_Sphere,GeomAbs_Torus):
            qualified=False;break
        explorer.Next()
    bucket.append((local,qualified))
    return qualified

def single_solid(shape):
    # DistShapeShape checks containment only when the top-level argument is
    # a SOLID. build123d Part wrappers can be one-solid compounds; passing
    # those directly reports a positive boundary gap for nested boxes.
    if shape.ShapeType()==TopAbs_SOLID:return shape
    explorer=TopExp_Explorer(shape,TopAbs_SOLID)
    if not explorer.More():return None
    solid=explorer.Current();explorer.Next()
    return None if explorer.More() else solid

def separation(a,b):
    a,b=single_solid(a),single_solid(b)
    if a is None or b is None:return None
    # General rational surface extrema are much slower than an exact Common
    # on these sculpted frames. Restrict this optional shortcut to small
    # analytic solids; every other pair proceeds to the ordinary Boolean.
    if not simple_analytic(a) or not simple_analytic(b):return None
    query=BRepExtrema_DistShapeShape()
    query.SetDeflection(1e-7)
    query.LoadS1(a);query.LoadS2(b);query.Perform()
    if not query.IsDone() or query.InnerSolution():return None
    distance=float(query.Value())
    return distance-1e-6 if distance>1e-6 else None
