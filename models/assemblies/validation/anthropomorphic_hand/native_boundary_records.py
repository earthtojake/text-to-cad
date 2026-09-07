"""Compare native support, topology and trim records without using Booleans.

Only native analytic or exact NURBS data is allowed. The scalar tolerance is
1e-10 in each stored field's units, not a global spatial/Hausdorff error bound.
Periodic trim records may differ by integer native periods. This report never
turns a failed Boolean result into a pass or certifies collision clearance.
"""
from copy import deepcopy
import math
from OCP.BRep import BRep_Tool
from OCP.BRepTools import BRepTools,BRepTools_WireExplorer
from OCP.TopAbs import TopAbs_EDGE,TopAbs_FACE,TopAbs_VERTEX,TopAbs_WIRE
from OCP.TopExp import TopExp,TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from cadgen._internal.surface_extract import _Bin,_surface_payload,_curve2d_payload,_curve3d_payload

ARRAY_KEYS={'poles','weights','knots','knotsU','knotsV'}
def expand(data,values):
    if isinstance(data,dict):
        return {k:(values[v[0]:v[0]+v[1]] if k in ARRAY_KEYS else expand(v,values)) for k,v in data.items()}
    if isinstance(data,list):return [expand(v,values) for v in data]
    return data

def payload(func,*args):
    buffer=_Bin();data=func(*args,buffer)
    return expand(data,buffer.values)

def signature(shape):
    edges=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape.wrapped,TopAbs_EDGE,edges)
    edge_data=[]
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        data=payload(_curve3d_payload,edge)
        assert data is not None or BRep_Tool.Degenerated_s(edge), 'Missing nondegenerate 3D curve'
        edge_data.append(data)
    faces=[]
    for face in shape.faces():
        f=face.wrapped;surface=BRep_Tool.Surface_s(f)
        kind=str(BRepAdaptor_Surface(f).GetType())
        assert any(kind.endswith(n) for n in ('Plane','Cylinder','Cone','Sphere','Torus','BSplineSurface','BezierSurface','SurfaceOfRevolution','SurfaceOfExtrusion')),kind
        periods=[surface.UPeriod() if surface.IsUPeriodic() else 0.,surface.VPeriod() if surface.IsVPeriodic() else 0.]
        loops=[];wire_exp=TopExp_Explorer(f,TopAbs_WIRE)
        while wire_exp.More():
            wire=TopoDS.Wire_s(wire_exp.Current());walker=BRepTools_WireExplorer(wire,f);loop=[]
            while walker.More():
                e=walker.Current();data=payload(_curve2d_payload,e,f)
                lo,hi=data['range'];span=hi-lo
                data['knots']=[(k-lo)/span for k in data['knots']];data['range']=[0.,1.]
                data.setdefault('weights',[1.]*data['n'])
                loop.append(dict(edge=edges.FindIndex(e),orientation=str(e.Orientation()),curve=data))
                walker.Next()
            if loop:
                start=min(range(len(loop)),key=lambda i:(loop[i]['edge'],loop[i]['orientation']))
                loop=loop[start:]+loop[:start]
            loops.append(loop);wire_exp.Next()
        loops.sort(key=lambda loop:[(r['edge'],r['orientation']) for r in loop])
        faces.append(dict(kind=kind,orientation=str(f.Orientation()),surface=payload(_surface_payload,f),
                          periods=periods,bounds=list(BRepTools.UVBounds_s(f)),loops=loops))
    return dict(edges=edge_data,faces=faces,vertices=[list(v.center()) for v in shape.vertices()],
                solids=len(shape.solids()),shells=len(shape.shells()))

def compare(a,b,epsilon=1e-10):
    first,second=signature(a),signature(b)
    if len(first['faces'])!=len(second['faces']):return dict(agrees=False,reason='face count')
    for fa,fb in zip(first['faces'],second['faces']):
        for axis,period in enumerate(fa['periods']):
            if not period:continue
            left=(fa['bounds'][2*axis]+fa['bounds'][2*axis+1])/2
            right=(fb['bounds'][2*axis]+fb['bounds'][2*axis+1])/2
            shift=round((left-right)/period)*period
            fb['bounds'][2*axis]+=shift;fb['bounds'][2*axis+1]+=shift
            for loop in fb['loops']:
                for row in loop:
                    p=row['curve']['poles']
                    for i in range(axis,len(p),2):p[i]+=shift
            if fb['surface']['kind']=='nurbs':
                key='knotsU' if axis==0 else 'knotsV'
                fb['surface'][key]=[k+shift for k in fb['surface'][key]]
    mismatches=[];maximum=[0.,None]
    def walk(x,y,path):
        if isinstance(x,(int,float)) and not isinstance(x,bool) and isinstance(y,(int,float)) and not isinstance(y,bool):
            error=abs(x-y)
            if error>maximum[0]:maximum[:]=[error,path]
            if error>epsilon:mismatches.append(dict(path=path,left=x,right=y,error=error))
        elif type(x)!=type(y):mismatches.append(dict(path=path,reason='type'))
        elif isinstance(x,dict):
            if x.keys()!=y.keys():mismatches.append(dict(path=path,reason='keys',left=list(x),right=list(y)))
            else:
                for key in x:walk(x[key],y[key],path+'/'+str(key))
        elif isinstance(x,list):
            if len(x)!=len(y):mismatches.append(dict(path=path,reason='count',left=len(x),right=len(y)))
            else:
                for i,(u,v) in enumerate(zip(x,y)):walk(u,v,path+'/'+str(i))
        elif x!=y:mismatches.append(dict(path=path,left=x,right=y))
    walk(first,second,'')
    return dict(agrees=not mismatches,epsilon=epsilon,maximum_scalar_difference=maximum[0],
                maximum_difference_path=maximum[1],mismatches=mismatches)
