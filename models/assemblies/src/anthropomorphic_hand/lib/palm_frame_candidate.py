"""Route-reserved skeletal palm, with one connected load-bearing body.

The fixed paths are solved around the full neutral tendon field and wrist-pose
curve field. Circular bearing seats and the dorsal CMC comb rail remain on the
original datums. No tendon, pulley or finger geometry is modified here.
"""
from cadgen import build123d as bd,srgb,report
from .palm_frame_paths import PALM_PATHS
from .layout import MCP_PALM_SUPPORT_PLANES,CMC_PALM_SUPPORT_PLANES

PALM_MOUNT_CENTERS=((-24.,14.,-10.2),(24.,14.,-10.2))
PALM_PAD_MOUNTS=((-24.,55.,11.5),(15.,53.,11.5),(-4.,66.,11.5))
CUP_AXIS=((22.,40.,0.),(0.,-1.,0.))
MULTI_EDGE_BRANCHES={row['name'] for row in PALM_PATHS}

def _eye(center,radius,thickness,axis='z'):
    s=bd.Cylinder(radius,thickness)
    s=s.chamfer(.20,None,s.edges())
    if axis=='y':s=bd.Rot(90,0,0)*s
    return bd.Pos(*center)*s

def _sweep(segments,radius):
    # One exact C2 B-spline spine avoids split pipe faces at every design knot.
    # Removing redundant knot multiplicity changes neither the centerline nor
    # its reserved tendon-clearance envelope (1e-9 mm conversion tolerance).
    from OCP.Geom import Geom_BSplineCurve
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfReal,TColStd_Array1OfInteger
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    poles=list(segments[0])+[p for segment in segments[1:] for p in segment[1:]]
    pp=TColgp_Array1OfPnt(1,len(poles))
    for i,p in enumerate(poles,1):pp.SetValue(i,gp_Pnt(*p))
    n=len(segments);kk=TColStd_Array1OfReal(1,n+1);mm=TColStd_Array1OfInteger(1,n+1)
    for i in range(n+1):kk.SetValue(i+1,i/n);mm.SetValue(i+1,4 if i in (0,n) else 3)
    curve=Geom_BSplineCurve(pp,kk,mm,3,False)
    for i in range(curve.NbKnots()-1,1,-1):curve.RemoveKnot(i,1,1e-9)
    edge=bd.Edge(BRepBuilderAPI_MakeEdge(curve).Edge())
    section=bd.Plane(origin=edge.position_at(0),z_dir=edge.tangent_at(0))*bd.Circle(radius)
    return bd.sweep(section,path=edge)

def make_palm_frame_bodies(mcp_support_plane=None,thumb_support_plane=None):
    if mcp_support_plane not in (None,MCP_PALM_SUPPORT_PLANES) or thumb_support_plane not in (None,CMC_PALM_SUPPORT_PLANES):
        raise ValueError('This frame preserves the current fixed support planes')
    pieces=[];bores=[]
    for row in PALM_PATHS:
        report(row['name'])
        if row['name'] in MULTI_EDGE_BRANCHES:
            edges=[bd.Edge.make_bezier(*v) for v in row['segments']];wire=bd.Wire(edges)
            section=bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(row['radius'])
            p=bd.sweep(section,path=wire)
        else:p=_sweep(row['segments'],row['radius'])
        if not p.is_valid or len(p.solids())!=1:raise ValueError(row['name'])
        pieces.append(p)
    # Three shallow branching nodes close the dorsal load arch.
    for c in ((-28,48,-22),(-10,74,-22),(16,56,-22)):
        pieces.append(bd.Pos(*c)*bd.Sphere(1.65))
    for x,y in ((-36,101),(-12,105),(12,100)):
        for z in MCP_PALM_SUPPORT_PLANES:
            c=(x,y,z);pieces.append(_eye(c,3.75,2));bores.append((c,2.53,6,'z'))
    for z in CMC_PALM_SUPPORT_PLANES:
        c=(-35,36,z);pieces.append(_eye(c,4.15,2));bores.append((c,2.53,6,'z'))
    for c in PALM_MOUNT_CENTERS:
        pieces.append(_eye(c,3.05 if c[0]<0 else 3.3,3.2));bores.append((c,1.65,8,'z'))
    for y in (35.,75.):
        c=(22.,y,0.);pieces.append(_eye(c,4.1,2.4,'y'));bores.append((c,2.53,5,'y'))
    for c in PALM_PAD_MOUNTS:
        pieces.append(_eye(c,2.5,2.2));bores.append((c,.8,7,'z'))
    # Exact original CMC dorsal rail: de Casteljau left half of the original
    # cubic retains the removable parent comb's native seating patch.
    pieces.append(_sweep([[(-35,36,-18),(-32.12,34.92,-18),(-28.7216,34.8768,-18),(-25.457984,35.543808,-18)]],1.3))
    pieces.append(bd.Pos(-25.457984,35.543808,-18)*bd.Sphere(1.3))
    s=pieces[0]
    for i,p in enumerate(pieces[1:],1):
        report(f'fuse load path {i}/{len(pieces)-1}')
        s=s.fuse(p)
        if not s.is_valid:raise ValueError(f'invalid fusion {i}')
    for c,r,h,axis in bores:
        cutter=bd.Cylinder(r,h)
        if axis=='y':cutter=bd.Rot(90,0,0)*cutter
        s=s-(bd.Pos(*c)*cutter)
    # The protruding rib neck must not foul the flanged bushings outside the
    # planar bearing faces. The full 2 mm cylindrical sleeve seats stay intact.
    for x,y,planes in [(-36,101,MCP_PALM_SUPPORT_PLANES),(-12,105,MCP_PALM_SUPPORT_PLANES),(12,100,MCP_PALM_SUPPORT_PLANES),(-35,36,CMC_PALM_SUPPORT_PLANES)]:
        for z in planes:
            sign=1 if z>0 else -1
            s=s-(bd.Pos(x,y,z+sign*3)*bd.Cylinder(2.8,4))
    # Full rotational clearance of the CMC negative yaw terminal pulley.
    # Its radius-8 envelope lies above the preserved Z=-18 bearing seat.
    s=s-(bd.Pos(-35,36,-13.5)*bd.Cylinder(8.,1.8))
    from .palm_frame_reliefs import relieve_frame
    s=relieve_frame(s)
    # Keep the already validated removable jaw system. Their exact negative
    # contact pockets cut only the branch entries outside the bearing seats.
    from pathlib import Path
    from cadgen import read_step
    source=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/palm_guide_mounts_review.step'
    def leaves(v):return [p for c in v.children for p in leaves(c)] if v.children else [v]
    jaws=[p for p in leaves(read_step(source)) if '_palm_bank_structural_body' in p.label]
    for jaw in jaws:s=s-jaw
    source=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step'
    for jaw in leaves(read_step(source)):
        if jaw.label=='thumb_cmc_parent_inlet_comb_structural_jaw':s=s-jaw
    # The fixed comb's outer M0.6 clamp screw remains removable in +Z.
    # Its head is outside the original dorsal seating patch; reserve 0.05 mm
    # around the head where the new thumb load branch passes alongside it.
    comb_screw_clearance=bd.Pos(-35,36,0)*bd.Rot(0,0,45)*bd.Pos(.26,-8,-16.9)*bd.Cylinder(.55,4.0)
    s=s-comb_screw_clearance
    from .wrist import make_wrist_palm_cradle
    s=s-make_wrist_palm_cradle()
    if not s.is_valid or len(s.solids())!=1:raise ValueError(('frame integrity',s.is_valid,len(s.solids()),[(round(x.volume,8),str(x.bounding_box())) for x in s.solids()]))
    s.label='palm_metacarpal_truss';s.color=srgb('#a9b7c1')
    s.cad_material={'roughness':.34,'metalness':.86,'clearcoat':.12}
    return [s]

def make_palm_frame(mcp_support_plane=None,thumb_support_plane=None,label='palm_frame_system'):
    return bd.Compound(label=label,children=make_palm_frame_bodies(mcp_support_plane,thumb_support_plane))
