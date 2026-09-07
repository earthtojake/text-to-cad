"""A monolithic skeletal MCP/CMC gimbal, local distal direction +Y.

The carrier rotates about Z and carries two outboard X-axis bearing eyes.
Neither orthogonal shaft traverses the tendon transport corridor. Four curved
load-path ribbons join the peripheral flex eyes to the outboard yaw hubs.
"""
from cadgen import build123d as bd, srgb
from .layout import MCP_YAW_HUB_PLANES,CMC_YAW_HUB_PLANES
from .phalanx import _drive_bore


def _rib(points):
    path=bd.Edge.make_bezier(*points)
    plane=bd.Plane(origin=path.position_at(0),z_dir=path.tangent_at(0))
    return bd.sweep(plane*bd.Ellipse(.64,.66),path=path)


def make_universal_carrier(phalanx_width=18.,yaw_plane=8.,
                           label='skeletal_universal_joint_carrier',hub_planes=None):
    """Single aluminum solid, bearing bore Ø5.06 at X±(width/2+1).

    Flex eyes are 1.9 thick: inner face is 0.05 outside the phalanx cheek.
    Hub planes come from the shared dorsal-stack layout, or explicit
    hub_planes=(palmar_z,dorsal_z). Hubs are 1.40 thick with integral D
    drive bores radius1.03 and flat Y+.75; flex bearing bores stay round.
    yaw_plane=9.5 selects the CMC layout; 8 selects the MCP layout.
    """
    x=phalanx_width/2+1.
    planes=tuple(hub_planes if hub_planes is not None else
                 CMC_YAW_HUB_PLANES if yaw_plane>8.5 else MCP_YAW_HUB_PLANES)
    if len(planes)!=2 or not planes[0]>0>planes[1]:
        raise ValueError("hub_planes must contain palmar positive and dorsal negative Z")
    pieces=[]
    for sign in (-1,1):
        ring=bd.Cylinder(3.75,1.9)-bd.Cylinder(2.53,3.9)
        ring=bd.fillet(ring.edges(),.19)
        pieces.append(bd.Pos(sign*x,0,0)*bd.Rot(0,90,0)*ring)
    for z in planes:
        # Palmar shoulders taper laterally beside the two PIP reaction
        # liners as those liners rise vertically at full flexion.
        hub=(bd.Pos(0,0,-.7)*bd.extrude(bd.SlotOverall(5.4,4.6,rotation=90),amount=1.4)
             if z>0 else bd.Cylinder(2.70,1.4))
        hub=bd.fillet(hub.edges(),.18)
        pieces.append(bd.Pos(0,0,z)*hub)
    for sx in (-1,1):
        for z in planes:
            sz=1 if z>0 else -1
            z=abs(z)
            if sz<0:
                # Dive beside the cheek before turning beneath the phalanx.
                # The entire deep bow remains distal of the fixed yaw input.
                points=[(sx*x,2.90,-1.25),(sx*x,4.,-2.5),
                        (sx*x,5.,-9.),(sx*x,9.,-(z+3.0)),
                        (sx*3.,5.,-(z+1.5)),(sx*1.2,1.85,-z)]
            else:
                points=[(sx*x,-2.90,1.25),(sx*x,-10.7,3.0),
                        (sx*5.8,-10.7,z+1.5+max(0.,yaw_plane-8.)*1.3),
                        (sx*1.2,-1.85,z)]
            pieces.append(_rib(points))
    frame=pieces[0].fuse(*pieces[1:])
    if len(frame.solids())!=1:
        raise ValueError(f'{label}: expected one aluminum solid, got {len(frame.solids())}: {[(s.volume,str(s.bounding_box())) for s in frame.solids()]}')
    roots=[e for e in frame.edges() if e.geom_type==bd.GeomType.BSPLINE
           and 1<e.length<4 and abs(e.center().Y) > 2.5]
    if roots:frame=bd.fillet(roots,.12)
    # Reopen journal bores after the ribbons meet their bearing bosses.
    for sign in (-1,1):
        frame=frame-(bd.Pos(sign*x,0,0)*bd.Rot(0,90,0)*bd.Cylinder(2.53,3.9))
    for z in planes:
        frame=frame-(bd.Pos(0,0,z-.725)*bd.Rot(0,0,90)*_drive_bore(1.03,.75))
    rims=[e for e in frame.edges() if e.bounding_box().size.Z<1e-6
          and abs(e.center().X)<1.04 and abs(e.center().Y)<1.04]
    frame=bd.fillet(rims,.08)
    frame.label=label
    frame.color=srgb('#a9b7c1')
    frame.cad_material={'roughness':.34,'metalness':.86,'clearcoat':.12}
    bounds=frame.bounding_box()
    if bounds.min.X > -x-.9 or bounds.max.X < x+.9:
        raise ValueError(f'{label}: Boolean result lost a bearing cheek')
    if not frame.is_valid or frame.volume<=0:raise ValueError(f'{label}: invalid carrier')
    return frame
