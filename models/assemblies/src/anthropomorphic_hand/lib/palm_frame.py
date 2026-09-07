"""Skeletal metacarpal bridge and independent fifth-ray cupping frame.

World datums; palm-facing +Z. The fifth ray is procedural; the single-body main frame is a validated native integration input.
Rounded load paths remain peripheral to the open tendon fan-out corridors.
"""
from cadgen import build123d as bd, srgb, report, read_step
from pathlib import Path
from .layout import MCP_PALM_SUPPORT_PLANES, CMC_PALM_SUPPORT_PLANES

PALM_MOUNT_CENTERS = ((-24.,14.,-10.2),(24.,14.,-10.2))
PALM_PAD_MOUNTS = ((-24.,55.,11.5),(15.,53.,11.5),(-4.,66.,11.5))
CUP_AXIS = ((22.,40.,0.), (0.,-1.,0.))


def _rib(points, radius=1.35):
    path=bd.Edge.make_bezier(*points)
    section=bd.Plane(origin=path.position_at(0),z_dir=path.tangent_at(0))*bd.Circle(radius)
    return bd.sweep(section,path=path)


def _eye(center,radius=3.75,bore=2.53,thickness=2.,axis='z'):
    s=bd.Cylinder(radius,thickness)
    s=bd.fillet(s.edges(),.20)
    if axis=='y':s=bd.Rot(90,0,0)*s
    return bd.Pos(*center)*s


def _root_fillet(shape,edges):
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    builder=BRepFilletAPI_MakeFillet(shape.wrapped)
    # Micron-scale surface approximation keeps tiny aesthetic blends tractable;
    # the exported solids still undergo the ordinary strict validity checks.
    builder.SetParams(.01,.001,.0001,.001,.0001,.001)
    for edge in edges:builder.Add(.03,edge.wrapped)
    builder.Build()
    if not builder.IsDone():raise ValueError('local fillet builder did not complete')
    result=bd.Part(builder.Shape())
    if not result.is_valid or len(result.solids())!=1:raise ValueError('local fillet returned invalid geometry')
    return result


def _blend_junctions(shape,nodes,label):
 for index,(x,y,z,radius) in enumerate(nodes):
  print('GROUP',index,flush=True)
  center=bd.Vector(x,y,z)
  edges=[e for e in shape.edges() if e.geom_type==bd.GeomType.BSPLINE and .5<e.length<30 and (e.position_at(.5)-center).length<radius]
  faces=list(shape.faces());junctions=[]
  for edge in edges:
   adjacent=[face for face in faces if any(edge.is_same(fe) for fe in face.edges())]
   if len(adjacent)!=2:continue
   normals=[face.normal_at(edge.position_at(.5)) for face in adjacent]
   if abs(normals[0].dot(normals[1]))<.99999:junctions.append(edge)
  edges=junctions
  if not edges:continue
  try:shape=shape.fillet(.03,edges)
  except Exception:
   pending=sorted(edges,key=lambda e:e.length,reverse=True)
   for attempt in range(3):
    failed=[];progress=False
    for edge in pending:
     if not any(edge.is_same(current) for current in shape.edges()):continue
     try:shape=shape.fillet(.03,[edge]);progress=True
     except Exception:failed.append(edge)
    pending=[edge for edge in failed if any(edge.is_same(current) for current in shape.edges())]
    if not pending or not progress:break
   if pending:
    faces=list(shape.faces())
    for e in pending:
     adjacent=[f for f in faces if any(e.is_same(fe) for fe in f.edges())]
     normals=[f.normal_at(e.position_at(.5)) for f in adjacent]
     print('UNRESOLVED',e.length,e.center(),[str(f.geom_type) for f in adjacent],normals[0].dot(normals[1]) if len(normals)==2 else 'seam',flush=True)
    raise ValueError((index,len(pending)))
 return shape

def _finish(pieces,label,bores,blend_nodes):
    s=pieces[0]
    for index,piece in enumerate(pieces[1:],1):
        if not piece.is_valid:raise ValueError(f'{label}: invalid primitive {index}')
        s=s.fuse(piece)
        if not s.is_valid or not len(s.solids()):raise ValueError(f'{label}: invalid fusion {index}')
    def cut_bores(shape,entries):
        for center,r,h,axis in entries:
            cutter=bd.Cylinder(r,h)
            if axis in ('y','yd'):
                cutter=bd.Rot(90,0,0)*cutter
                if axis=='yd':cutter=cutter-(bd.Pos(r+.75,0,0)*bd.Box(2*r,h+2,2*r+2))
            shape=shape-(bd.Pos(*center)*cutter)
            if not shape.is_valid:raise ValueError(f'{label}: invalid bore at {center}, radius {r}, axis {axis}')
        return shape
    # Bearing bores establish the root boundary before blending. The small
    # keyed drive bores sit inside the bosses and are broached afterward.
    s=cut_bores(s,[b for b in bores if b[3]!='yd'])
    s=_blend_junctions(s,blend_nodes,label)
    s=cut_bores(s,[b for b in bores if b[3]=='yd'])
    if len(s.solids())!=1:
        raise ValueError(f'{label}: {len(s.solids())} disconnected solids; bounds {[str(b.bounding_box()) for b in s.solids()]}')
    if not s.is_valid or s.volume<=0:raise ValueError(f'{label}: invalid frame')
    s.label=label;s.color=srgb('#a9b7c1')
    s.cad_material={'roughness':.34,'metalness':.86,'clearcoat':.12}
    return s


def _planes(value,default):
    if value is None:return tuple(default)
    if isinstance(value,(int,float)):return (float(value),-float(value))
    return tuple(value)


def make_little_metacarpal(mcp_support_plane=None,label='fifth_metacarpal_cupping_truss'):
    p=[];bores=[]
    mp=_planes(mcp_support_plane,MCP_PALM_SUPPORT_PLANES)
    for y in (38.2,71.8):
        c=(22.,y,0.);p.append(_eye(c,4.1,1.03,2.4,'y'));bores.append((c,1.03,5,'yd'))
    for sign in (-1,1):
        z=mp[0 if sign>0 else 1]
        from .palm_little_paths import LITTLE_PATHS
        p += [_rib(points,radius) for side,index,points,radius in LITTLE_PATHS if side==sign]
        c=(36,89,z);p.append(_eye(c));bores.append((c,2.53,5,'z'))
    nodes=[(22,y,sign*3.4,2.8) for y in (38.2,71.8) for sign in (1,-1)]
    nodes += [(36,89,z,5.) for z in mp]
    result=_finish(p,label,bores,nodes)
    result.label=label;result.color=srgb('#a9b7c1')
    result.cad_material={'roughness':.34,'metalness':.86,'clearcoat':.12}
    return result


def make_palm_frame_bodies(mcp_support_plane=None,thumb_support_plane=None):
    """Validated one-body integration geometry; evidence is in PALM_STATUS.md.

    Source construction is preserved in palm_frame_candidate.py. This declared
    STEP input prevents assembly integrations from repeating the route-reserved
    branch sweeps and native clearance pockets. Replacing it invalidates dependent CAD builds.
    """
    mp=_planes(mcp_support_plane,MCP_PALM_SUPPORT_PLANES)
    tp=_planes(thumb_support_plane,CMC_PALM_SUPPORT_PLANES)
    if mp!=tuple(MCP_PALM_SUPPORT_PLANES) or tp!=tuple(CMC_PALM_SUPPORT_PLANES):
        raise ValueError('Frozen palm integration geometry uses the current asymmetric layout support planes')
    path=Path(__file__).resolve().parents[3]/'STEP'/'anthropomorphic_hand'/'imported'/'palm_frame_integration.step'
    assembly=read_step(path)
    bodies=list(assembly.children)
    if len(bodies)!=1 or any(len(b.solids())!=1 for b in bodies):
        raise ValueError('Expected one connected main-palm solid')
    for body in bodies:
        aluminum=body.label=='palm_metacarpal_truss' or 'bearing_node' in body.label or 'clamp' in body.label
        body.color=srgb('#a9b7c1' if aluminum else '#d0d8df')
        body.cad_material={'roughness':.34 if aluminum else .16,'metalness':.86 if aluminum else .98}
    return bodies


def make_palm_frame(mcp_support_plane=None,thumb_support_plane=None,label='palm_frame_system'):
    return bd.Compound(label=label,children=make_palm_frame_bodies(mcp_support_plane,thumb_support_plane))
