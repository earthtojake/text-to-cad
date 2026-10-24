"""A single formed fixed jaw connects the cases of wrist servos 6 and 7.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

The sixth axis has fixed horns and a rotating case. Both case interfaces are
parallel: flat paired plates avoid a redundant sheet-metal collar. Gripper
orientation is unchanged; it translates outward and 0.5 mm up so the case-seat
planes coincide. Material 2.032 mm 5052-H32; shared gripper/link case-end profiles and equal widths.
"""
from __future__ import annotations
import math
import sys
from pathlib import Path
SRC=Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
import build123d as bd
from cadgen import read_step
from lib.mates import revolute, fastened
from lib.centered_gripper import with_centered_frame
from lib.legacy_base_support import INPUTS
from lib.servo_case_flange import case_hole_centers
from lib.servo_fit import SERVO
from lib.booleans import as_single_shape as one
from lib.materials import ALUMINUM_5052_COLOR,SCREW_COLOR
from lib.restored_frame_gauge import WALL_FACE_X_MM
from lib.gripper_frame_layout import GRIPPER_CARRIED_SHIFT_MM
from lib.restored_claw_refinement import GRIPPER_SHAFT_X_MM,GRIPPER_SHAFT_Y_MM,GRIPPER_CLOSE_ANGLE_DEG
from lib.gripper_horn_phase import moving_screw_xy,RECOVERED_JAW_BAND_SHIFT_Y_MM
from lib.screw_datums import BRACKET_SCREW_DATUMS,DATUM_SHEET_THICKNESS_MM
from hardware.hex_socket_cap import hex_socket_m2x6,hex_socket_m3x5
from lib.link_assembly import location_from_transform
from lib import camera_mount_geometry as g, camera_bends as bends
from lib.camera_mount_interface import cut_face
from camera.camera_payload import camera_payload
from functools import partial

ROOT=SRC.parent
T=2.032
# Same fixed wrist geometry retained by Tom2; millimetres, saved rest frame.
SIXTH_NATIVE_ORIGIN=(-118.62128375907787,0,81.575)
SIXTH_TRANSFORM=(-1,0,0,SIXTH_NATIVE_ORIGIN[0],0,0,-1,0,0,-1,0,SIXTH_NATIVE_ORIGIN[2],0,0,0,1)
def sixth_placement():
    return location_from_transform(SIXTH_TRANSFORM)
SIXTH_FAR_END_X=SIXTH_NATIVE_ORIGIN[0]-SERVO.middle_case_end_x_mm
# Reserve a 1.5 mm nominal case-to-case gap (bare aluminum, no coating).
# The old bridge datum left 8.643223311 mm between the vendor case envelopes.
# Keep that source datum explicit; the gripper translates without rotating.
CASE_GAP_MM=1.5
PREVIOUS_CASE_GAP_MM=8.643223311
GRIPPER_INSET_MM=PREVIOUS_CASE_GAP_MM-CASE_GAP_MM
# Advance both complete gripping sections 8 mm from the previous 5 mm
# inset. Retain their 60 mm faces and leave the case/horn interfaces fixed.
FINGER_INSET_MM=-3.0
STATIC_JAW_WALL_Y_MM=-9.5488
STATIC_JAW_OUTER_SHOULDER_Y_MM=-32.55
CAMERA_RISER_LENGTH_MM=23.1
CAMERA_RISER_HEADING_DEG=125.3
# Integrated tom2 support only; production tom.py retains its own camera pitch.
CAMERA_PANEL_PITCH_DEG=22.0
CAMERA_PANEL_BOTTOM_LAND_MM=6.0
# 20 mm casing opening + two 10 mm support legs. Retain the original
# 40 mm camera panel and 2.032 mm stock; narrowing is in-plane only.
CAMERA_SUPPORT_WIDTH_MM=40.0
CAMERA_ROOT_LAND_MM=5.0
CAMERA_CLEARANCE_WIDTH_MM=20.0
CAMERA_CLEARANCE_FLAT_LENGTH_MM=5.4
CAMERA_CLEARANCE_RISER_LENGTH_MM=18.0
GRIPPER_PLATE_END_X=SIXTH_FAR_END_X-2.5+GRIPPER_INSET_MM
NATIVE_PLATE_END_X=WALL_FACE_X_MM-(.9652+T)
GRIPPER_SHIFT=(GRIPPER_PLATE_END_X-NATIVE_PLATE_END_X,-29.532,91.175)


def claw_layout():
    """Close the existing moving finger on the wrist centerline (Y=0)."""
    from lib import restored_claw_refinement as c
    from lib.horn_cap import FRAME_HORN_CAP_DIAMETER_MM
    a=math.radians(c.FIXED_SLANT_ANGLE_DEG)
    target_x=(c.FIXED_BEND_ROOT_X_MM
        +(c.FIXED_PINCH_TIP_X_MM-c.FIXED_BEND_ROOT_X_MM)*math.cos(a)
        +GRIPPER_SHIFT[0]+FINGER_INSET_MM)
    cx=GRIPPER_SHAFT_X_MM+GRIPPER_SHIFT[0]
    cy=(GRIPPER_SHAFT_Y_MM+RECOVERED_JAW_BAND_SHIFT_Y_MM
        +GRIPPER_CARRIED_SHIFT_MM[1]+GRIPPER_SHIFT[1])
    radius=FRAME_HORN_CAP_DIAMETER_MM/2
    fold_y=cy-radius
    tip_y=fold_y-(.9652+T)
    # The reference tip must lie on the fixed tip's circle about the shaft.
    reach2=(target_x-cx)**2+cy**2
    tip_x=cx-math.sqrt(reach2-(tip_y-cy)**2)
    # Solve the moving phase at centerline contact; the fixed face mirrors
    # it now that both gripping-face roots are ahead of the casing.
    closing=math.degrees(math.atan2(-cy,target_x-cx)
                         -math.atan2(tip_y-cy,tip_x-cx))
    return cx,cy,target_x,tip_x,tip_y,fold_y,closing


def claw_contact():
    cx,cy,_,x,y,_,angle=claw_layout();a=math.radians(angle)
    return (cx+(x-cx)*math.cos(a)-(y-cy)*math.sin(a),
            cy+(x-cx)*math.sin(a)+(y-cy)*math.cos(a))


def static_claw_angle():
    # Once both face roots are clear of the casing, the fixed face can
    # mirror the moving face about Y=0 instead of stopping at the case wall.
    return claw_layout()[-1]


def inline_kinematics():
    """Original inline chain: S6 horns stay on the yoke; its case carries S7."""
    mates=[
        revolute('wristPitch',parent='#wrist_pitch_servo',child='#temporary_wrist_yoke',
                 origin=(-60.271283759077875,9.1,90.675),direction=(0,1,0),limits=(-97,70)),
        revolute('wristYaw',parent='#temporary_wrist_yoke',child='#wrist_yaw_servo',
                 origin=(SIXTH_NATIVE_ORIGIN[0]+25.5,0,90.675),direction=(0,0,1),limits=(-90,90)),
        revolute('gripperJaw',parent='#gripper_jaw_servo',child='#gripper_right_claw',
                 origin=(GRIPPER_SHAFT_X_MM+GRIPPER_SHIFT[0],
                         GRIPPER_SHAFT_Y_MM+RECOVERED_JAW_BAND_SHIFT_Y_MM+GRIPPER_CARRIED_SHIFT_MM[1]+GRIPPER_SHIFT[1],
                         GRIPPER_SHIFT[2]),direction=(0,0,-1),limits=(0,90)),
    ]
    def attach(child,parent):
        mates.append(fastened('carry_'+child,parent='#'+parent,child='#'+child))
    attach('temporary_wrist_screws','temporary_wrist_yoke')
    for servo in ('wrist_pitch_servo','wrist_yaw_servo'):
        for detail in (14,15,16):attach(f'{servo}_detail_{detail}','temporary_wrist_yoke')
    for child in ('servo6_fixed_gripper_frame',
                  'gripper_jaw_servo','gripper_connector_hardware','wrist_camera_payload'):
        attach(child,'wrist_yaw_servo')
    for child in ('inline_jaw_drive_horn','inline_jaw_idler_horn','OUTPUTGEAR','gripper_jaw_center_m3x5'):
        attach(child,'gripper_right_claw')
    for i in range(1,7):attach(f'gripper_right_claw__hex_socket_m3x5__{i:02d}','gripper_right_claw')
    return {'mates':mates,'poses':{
        'rest':{'wristPitch':0,'wristYaw':0,'gripperJaw':0},
        'jaw_open':{'wristPitch':0,'wristYaw':0,'gripperJaw':25},
        'straight_finger_reference':{'wristPitch':0,'wristYaw':0,'gripperJaw':claw_layout()[-1]},
        'motion_preview':{'wristPitch':20,'wristYaw':30,'gripperJaw':25},
        'wrist_minus_90':{'wristPitch':0,'wristYaw':-90,'gripperJaw':0},
        'wrist_plus_90':{'wristPitch':0,'wristYaw':90,'gripperJaw':0},
    }}


def box(lo,hi):return bd.Solid.make_box(*(b-a for a,b in zip(lo,hi)),bd.Plane(origin=lo))

def closed_native_gripper():
    """Same complete servo and claws, square horns and closed jaw reference."""
    g=with_centered_frame(read_step(INPUTS/'gripper.step'))
    # Hardware is fitted to the shared source profiles before closing the jaw.
    m2,m3=hex_socket_m2x6(),hex_socket_m3x5();hardware=[]
    lookup={p.label:p for p in g.children}
    for row in BRACKET_SCREW_DATUMS:
        parent=row['parent']
        if parent not in ('gripper_frame','gripper_left_claw','gripper_right_claw'):continue
        if parent=='gripper_frame' and abs(row['outward'][2])<.99:continue
        expected=[row['seat'][i]+row['outward'][i]*(T-DATUM_SHEET_THICKNESS_MM)+GRIPPER_CARRIED_SHIFT_MM[i] for i in range(3)]
        if parent=='gripper_right_claw':
            xy=moving_screw_xy(int(row['label'].rsplit('__',1)[1]));expected[:2]=[xy[i]+GRIPPER_CARRIED_SHIFT_MM[i] for i in range(2)]
        radius=1.1 if row['model']=='hex_socket_m2x6' else 1.6
        candidates=[e.arc_center for e in lookup[parent].edges() if e.geom_type==bd.GeomType.CIRCLE and abs(e.radius-radius)<1e-6]
        c=min(candidates,key=lambda p:sum((tuple(p)[i]-expected[i])**2 for i in range(3)))
        assert sum((tuple(c)[i]-expected[i])**2 for i in range(3))<1e-8
        q=(m2 if radius==1.1 else m3).moved(bd.Plane(origin=c,z_dir=row['outward']).location)
        q.label=row['label'];q.color=SCREW_COLOR
        hardware.append((q,parent=='gripper_right_claw'))
    axis=bd.Axis((GRIPPER_SHAFT_X_MM,GRIPPER_SHAFT_Y_MM+RECOVERED_JAW_BAND_SHIFT_Y_MM+GRIPPER_CARRIED_SHIFT_MM[1],0),(0,0,1))
    def clone(node,ancestor=None):
        if ancestor is None:ancestor=bd.Location()
        if node.children:
            return bd.Compound(children=[clone(c,ancestor*node.location) for c in node.children],label=node.label)
        q=bd.Compound.cast(node.wrapped).moved(ancestor);q.label=node.label;q.color=node.color
        if node.label in ('FK-AP-019-25T','WJ-DP00-0002-FK-AP-020','gripper_right_claw'):
            q=q.rotate(axis,GRIPPER_CLOSE_ANGLE_DEG)
        return q
    parts=[clone(p) for p in g.children]
    hardware=[p.rotate(axis,GRIPPER_CLOSE_ANGLE_DEG) if moving else p for p,moving in hardware]
    def leaves(n):
        if n.children:
            for c in n.children:yield from leaves(c)
        else:yield n
    drive=next(n for n in leaves(parts[1]) if n.label=='FK-AP-019-25T')
    candidates=[]
    for face in drive.faces():
        arcs=[e for e in face.edges() if e.geom_type==bd.GeomType.CIRCLE and abs(e.radius-1.6)<1e-6]
        if face.geom_type==bd.GeomType.PLANE and arcs:candidates.append((face.area,face,arcs[0].arc_center))
    _,face,center=max(candidates,key=lambda p:p[0])
    retainer=m3.moved(bd.Plane(origin=center,z_dir=face.normal_at()).location)
    retainer.label='gripper_jaw_center_m3x5';retainer.color=SCREW_COLOR;hardware.append(retainer)
    return parts,hardware


def connector_parts(native_frame):
    """Canonical jaw-case ends joined to the link plate's two-tab case ends.

    The S7 end is copied exactly from the maintained gripper frame's seat
    face, including its R11 horn relief. S6 follows the established link-end
    pattern: 2.65 mm beyond each hole, R1 free tips, square notch roots.
    Only the central notch width grows by 0.35 mm to clear this case cover.
    """
    from lib.corner_rules import OUTLINE_CORNER_R_MM
    pieces=[]
    for sign,side in ((1,'lower'),(-1,'upper')):
        seat=sign*16
        faces=[f for f in native_frame.faces()
               if f.geom_type==bd.GeomType.PLANE and abs(f.normal_at().Z)>.999
               and abs(f.center().Z-seat)<1e-6]
        face=max(faces,key=lambda f:f.area).moved(bd.Pos(*GRIPPER_SHIFT))
        jaw_end=bd.Solid.extrude(face,(0,0,sign*T))
        bounds=face.bounding_box();start=bounds.max.X
        ymin,ymax=bounds.min.Y,bounds.max.Y
        holes=[]
        for mirror in (-1,1):
            for p in case_hole_centers(side,mirror,reversible=False):
                if p[0]!=max(SERVO.case_lower_hole_x_mm if side=='lower' else SERVO.case_upper_hole_x_mm):continue
                c=bd.Vertex(*p).moved(sixth_placement()).center()
                holes.append((c.X,c.Y))
        end=holes[0][0]+2.65+(CAMERA_ROOT_LAND_MM if sign>0 else 0)
        z=GRIPPER_SHIFT[2]+seat
        # Union the two end profiles before opening the S6 window. Their
        # forming lands may overlap when the cases are brought together.
        points=[(start-.01,ymin,z),(end,ymin,z),
                (end,ymax,z),(start-.01,ymax,z)]
        extension=bd.Face(bd.Wire.make_polygon(points,close=True))
        plate=one(jaw_end.fuse(bd.Solid.extrude(extension,(0,0,sign*T))))
        zmin=min(z,z+sign*T)
        if sign<0:
            # Only the lower case cover protrudes into this sheet: its rib
            # is 1.1 mm proud, between Y +/-7. Keep 0.35 mm lateral room.
            root=SIXTH_NATIVE_ORIGIN[0]-max(SERVO.case_upper_hole_x_mm)-7.11
            plate=one(plate.cut(box((root,-7.35,zmin-.01),
                                   (end+1,7.35,zmin+T+.01))))
        profile=max((f for f in plate.faces() if f.geom_type==bd.GeomType.PLANE
                     and abs(f.center().Z-z)<1e-6 and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        if sign<0:
            tips=[v for v in profile.vertices() if abs(v.center().X-end)<1e-6]
            profile=profile.fillet_2d(OUTLINE_CORNER_R_MM,tips)
        plate=bd.Solid.extrude(profile,(0,0,sign*T))
        for x,y in holes:
            plate=plate.cut(bd.Solid.make_cylinder(1.1,T+.02,bd.Plane(origin=(x,y,zmin-.01))))
        plate=one(plate).clean()
        assert plate.is_valid and len(plate.solids())==1
        plate.label='servo6_gripper_upper_plate' if sign>0 else 'servo6_gripper_lower_plate'
        plate.color=ALUMINUM_5052_COLOR
        pieces.append(plate)
    return pieces


def make_connector():
    native,hardware=closed_native_gripper()
    plates=connector_parts(native[0].solids()[0])
    gripper=[p.moved(bd.Pos(*GRIPPER_SHIFT)) for p in native[1:]]
    for i,p in enumerate(gripper):
        if p.label in ('gripper_left_claw','gripper_right_claw'):
            gripper[i]=inset_finger(p,FINGER_INSET_MM)
    axis=bd.Axis((*claw_layout()[:2],GRIPPER_SHIFT[2]),(0,0,1))
    closing=claw_layout()[-1]
    for i,p in enumerate(gripper):
        if p.label=='gripper_right_claw':
            gripper[i]=rear_opening_claw(p)
    moving=next(p for p in gripper if p.label=='gripper_right_claw')
    for i,p in enumerate(gripper):
        if p.label=='gripper_left_claw':gripper[i]=matched_static_claw(p,moving)
    def label_horns(node,ancestor=None):
        if ancestor is None:ancestor=bd.Location()
        aliases={'FK-AP-019-25T':'inline_jaw_drive_horn','WJ-DP00-0002-FK-AP-020':'inline_jaw_idler_horn'}
        if node.children:
            return bd.Compound(children=[label_horns(c,ancestor*node.location)
                                         for c in node.children],label=node.label)
        q=bd.Compound.cast(node.wrapped).moved(ancestor)
        q.label=aliases.get(node.label,node.label);q.color=node.color
        if q.label in (*aliases.values(),'OUTPUTGEAR'):q=q.rotate(axis,closing)
        return q
    gripper=[label_horns(part) for part in gripper]
    hardware=[p.moved(bd.Pos(*GRIPPER_SHIFT)) for p in hardware]
    hardware=[p.rotate(axis,90+closing) if p.label.startswith('gripper_right_claw__')
              else p for p in hardware]
    fixed=next(p for p in gripper if p.label=='gripper_left_claw')
    combined=combined_fixed_frame(fixed,plates)
    gripper=[p for p in gripper if p.label!='gripper_left_claw']
    # The lower return (selected e25/e51) and its two screws are obsolete.
    hardware=[p for p in hardware if p.label not in (
        'gripper_left_claw__hex_socket_m2x6__02',
        'gripper_left_claw__hex_socket_m2x6__03')]
    m2=hex_socket_m2x6()
    for side in ('lower','upper'):
        for sign in (-1,1):
            for p in case_hole_centers(side,sign,reversible=False):
                if p[0]!=max(SERVO.case_lower_hole_x_mm if side=='lower' else SERVO.case_upper_hole_x_mm):continue
                outward=(0,-1 if side=='lower' else 1,0)
                seat=tuple(p[i]+T*outward[i] for i in range(3))
                q=m2.moved(bd.Plane(origin=seat,z_dir=outward).location).moved(sixth_placement())
                q.label=f'servo6_case_m2x6_{len(hardware)+1}';q.color=SCREW_COLOR;hardware.append(q)
    combined,camera=integrated_camera(combined,plates[0])
    return [combined]+gripper+[bd.Compound(children=hardware,label='gripper_connector_hardware'),camera]


def combined_fixed_frame(fixed,plates):
    """Join coplanar cheeks into one sheet, retaining the jaw's two bends.

    The return on the far side of S7 is removed; both sheets now carry the
    fixed jaw directly into the four S7 and four S6 case fasteners.
    """
    b=fixed.bounding_box();end=b.max.X;outer_y=b.min.Y
    # Bounds of the selected lower case return, relative to the claw end.
    fixed=one(fixed.cut(box((end-16.3625766945-.01,-15,b.min.Z-.01),
                            (end-11.672+.01,16,b.min.Z+T+.01))))
    pieces=[fixed,*plates]
    for plate in plates:
        pb=plate.bounding_box();z=pb.min.Z
        # Broad straight load path behind S7; a single diagonal runs out to
        # the S6 mounting width. All seams lie inside this common outline.
        pts=[(end-4,outer_y,z),(end,outer_y,z),
             (pb.max.X,-14.6828,z),(pb.max.X,-9.5488,z)]
        if z<b.min.Z+T:
            # Lower case cover has a raised rib. Continue the established
            # fixed-claw clearance edge until 0.5 mm past that rib's end.
            pts.extend([(end+3.5,-9.5488,z),(end+3.5,-14.9752,z),
                        (end-4,-14.9752,z)])
        else:
            pts.append((end-4,-9.5488,z))
        face=bd.Face(bd.Wire.make_polygon(pts,close=True))
        pieces.append(bd.Solid.extrude(face,(0,0,T)))
    result=one(pieces[0].fuse(*pieces[1:])).clean()
    # Carry the finger's single straight perimeter all the way to the
    # mounting shoulder, cutting away the former intermediate flat.
    outer_edges=[e for e in fixed.edges()if e.geom_type==bd.GeomType.LINE
                 and e.length>40 and abs(e.tangent_at().Z)<1e-6
                 and e.center().Y< -15]
    edge=max(outer_edges,key=lambda e:e.length)
    p0,p1=[v.center()for v in edge.vertices()]
    def line_y(x):return p0.Y+(x-p0.X)*(p1.Y-p0.Y)/(p1.X-p0.X)
    mask=bd.Face(bd.Wire.make_polygon([(-300,line_y(-300),b.min.Z-1),
        (0,line_y(0),b.min.Z-1),(0,200,b.min.Z-1),(-300,200,b.min.Z-1)],close=True))
    result=one(result.intersect(bd.Solid.extrude(mask,(0,0,b.size.Z+2)))).clean()
    shoulder_edges=[e for e in result.edges()if e.geom_type==bd.GeomType.LINE
        and abs(e.length-T)<1e-5 and abs(e.center().X-end)<1e-5
        and abs(e.center().Y-line_y(end))<1e-5]
    assert len(shoulder_edges)==2
    result=result.fillet(3.0,shoulder_edges).clean()
    # Recut existing M2 bores through the new joining stock.
    holes=[]
    for part in [fixed,*plates]:
        for e in part.edges():
            if e.geom_type==bd.GeomType.CIRCLE and abs(e.radius-1.1)<1e-6:
                c=e.arc_center
                z=b.min.Z if c.Z<(b.min.Z+b.max.Z)/2 else b.max.Z-T
                key=tuple(round(v,6) for v in (c.X,c.Y,z))
                if key not in holes:holes.append(key)
    for x,y,z in holes:
        result=one(result.cut(bd.Solid.make_cylinder(1.1,T+.02,
                    bd.Plane(origin=(x,y,z-.01)))))
    result=result.clean()
    assert result.is_valid and len(result.solids())==1
    result.label='servo6_fixed_gripper_frame';result.color=ALUMINUM_5052_COLOR
    return result


def inset_finger(claw,delta):
    """Translate the gripping web and bends; redraw cheeks to fixed mounts.

    Length, angle and mutual closed-pose alignment of the gripping surfaces
    are invariant. The servo holes, horn profile and rotation axis stay put.
    """
    b=claw.bounding_box()
    faces=[]
    core=claw
    for z,dz in ((b.min.Z,T),(b.max.Z,-T)):
        face=max((f for f in claw.faces() if f.geom_type==bd.GeomType.PLANE
                  and abs(f.center().Z-z)<1e-5 and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        faces.append((face,dz))
        # Subtract only the planar sheet footprint, preserving the complete
        # quarter bends (a bounding slab would shave their curved sectors).
        core=one(core.cut(bd.Solid.extrude(face,(0,0,dz))))
    cutoff=core.bounding_box().max.X+1e-5
    def pt(v):
        return v+bd.Vector(delta,0,0) if v.X<cutoff else v
    pieces=[core.moved(bd.Pos(delta,0,0))]
    for face,dz in faces:
        edges=[]
        for edge in face.outer_wire().edges():
            vs=[v.center() for v in edge.vertices()]
            shifts=[v.X<cutoff for v in vs]
            if all(shifts):edge=edge.moved(bd.Pos(delta,0,0))
            elif any(shifts):
                assert edge.geom_type==bd.GeomType.LINE,'Inset crosses an outline arc'
                edge=bd.Edge.make_line(pt(vs[0]),pt(vs[1]))
            edges.append(edge)
        profile=bd.Face(bd.Wire.combine(edges)[0],face.inner_wires())
        pieces.append(bd.Solid.extrude(profile,(0,0,dz)))
    result=one(pieces[0].fuse(*pieces[1:])).clean()
    if not result.is_valid:result=result.fix()
    assert result.is_valid and len(result.solids())==1, (claw.label,cutoff,result.is_valid,len(result.solids()))
    result.label=claw.label;result.color=claw.color
    return result


def rear_opening_claw(claw):
    """Retain the formed gripping web; replace both complete cheek outlines.

    The fork opens toward +X and uses the two side holes and forward hole.
    Its flat inner edge continues straight into the finger's bend tangent.
    The outer edge stays parallel to the gripping face before a 45-degree tip cap.
    """
    from lib.horn_cap import apply_horn_fork,CIRCULAR_HORN_FORK_PATTERN
    from lib.restored_claw_refinement import TIP_TAPER_FLAT_LAND_MM
    cx,cy,target_x,tip_x,tip_y,fold_y,closing=claw_layout()
    b=claw.bounding_box();core=claw
    for z,dz in ((b.min.Z,T),(b.max.Z,-T)):
        face=max((f for f in claw.faces() if f.geom_type==bd.GeomType.PLANE
                  and abs(f.center().Z-z)<1e-5 and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        core=one(core.cut(bd.Solid.extrude(face,(0,0,dz))))
    core=core.rotate(bd.Axis((target_x,0,0),(0,0,1)),-GRIPPER_CLOSE_ANGLE_DEG)
    core=core.moved(bd.Pos(tip_x-target_x,tip_y,0))
    # The outer Z plane of the quarter bend gives the exact fold endpoint.
    tangent=[v.center() for v in core.vertices() if abs(v.center().Z-b.max.Z)<1e-5]
    nose=min(v.X for v in tangent)
    assert max(abs(v.Y-fold_y) for v in tangent)<1e-5
    pieces=[core]
    for z in (b.min.Z,b.max.Z-T):
        outer=(nose,fold_y+TIP_TAPER_FLAT_LAND_MM+1.0)
        r=CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm
        # Stay parallel to the gripping bend at the horn's outer tangent.
        # Only the last segment narrows: equal run/rise makes a 45 degree cap.
        outer_y=cy+r
        knee=(nose+outer_y-outer[1],outer_y)
        bend_root=max(v.X for v in tangent)
        pts=[(nose,fold_y),(bend_root,fold_y),(cx,cy-r),
             (cx,outer_y),knee,outer]
        face=bd.Face(bd.Wire.make_polygon([(x,y,z)for x,y in pts],close=True))
        face=face.fillet_2d(1.0,[v for v in face.vertices()
                               if (abs(v.center().X-nose)<1e-5 and v.center().Y>fold_y+.01)
                               or (v.center()-bd.Vector(knee[0],knee[1],z)).length<1e-5])
        cheek=bd.Solid.extrude(face,(0,0,T))
        cap=bd.Solid.make_cylinder(r,T,bd.Plane(origin=(cx,cy,z)))
        cheek=one(cheek.fuse(cap)).clean()
        cheek=apply_horn_fork(cheek,center=(cx,cy,z+T/2),
            across=(0,1,0),outboard=(1,0,0),normal=(0,0,1),
            thickness_mm=T,half_width_mm=r,pattern=CIRCULAR_HORN_FORK_PATTERN)
        pieces.append(cheek)
    result=one(pieces[0].fuse(*pieces[1:])).clean()
    if not result.is_valid:result=result.fix()
    assert result.is_valid and len(result.solids())==1
    result=result.rotate(bd.Axis((cx,cy,0),(0,0,1)),closing)
    result.label=claw.label;result.color=claw.color
    return result


def matched_static_claw(claw,moving):
    """Mirror the constant-width moving finger and its 45-degree tip cap.

    Both 60 mm gripping webs meet on Y=0 with equal opposing angles.
    Their roots are ahead of the casing, joined to the retained case lands.
    """
    b=claw.bounding_box();core=claw;faces=[]
    for z,dz in ((b.min.Z,T),(b.max.Z,-T)):
        face=max((f for f in claw.faces() if f.geom_type==bd.GeomType.PLANE
                  and abs(f.center().Z-z)<1e-5 and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        faces.append((face,dz))
        core=one(core.cut(bd.Solid.extrude(face,(0,0,dz))))
    _,_,old_x,_,_,_,moving_angle=claw_layout();tx,ty=claw_contact()
    angle=static_claw_angle()
    core=core.rotate(bd.Axis((old_x,0,0),(0,0,1)),GRIPPER_CLOSE_ANGLE_DEG-angle)
    core=core.moved(bd.Pos(tx-old_x,ty,0))
    mb=moving.bounding_box()
    moving_face=max((f for f in moving.faces() if f.geom_type==bd.GeomType.PLANE
        and abs(f.center().Z-mb.max.Z)<1e-5),key=lambda f:f.area)
    mirror=bd.Plane(origin=(0,ty,0),x_dir=(1,0,0),z_dir=(0,1,0))
    mirrored=moving_face.mirror(mirror).rotate(
        bd.Axis((tx,ty,0),(0,0,1)),moving_angle-angle)
    # At the original case outline the front taper joins the stationary
    # header. No horn-cap geometry or bolt holes enter this fixed finger.
    split=GRIPPER_SHAFT_X_MM+GRIPPER_SHIFT[0]-12.3625766945
    # Mirror the entire constant-width fingertip, including its 45 degree
    # nose cap; only its mounting header is unique to the stationary jaw.
    front_face=max(one(mirrored.intersect(box((-500,-100,mb.max.Z-1),
        (split,100,mb.max.Z+1)))).faces(),key=lambda f:f.area)
    lines=[e for e in mirrored.outer_wire().edges() if e.geom_type==bd.GeomType.LINE]
    outer=min((e for e in lines if e.length>40),key=lambda e:e.center().Y)
    p,q=[v.center() for v in outer.vertices()]
    def outer_y_at(x):return p.Y+(x-p.X)*(q.Y-p.Y)/(q.X-p.X)
    parts=[core]
    for face,dz in faces:
        z=face.center().Z
        front=bd.Solid.extrude(front_face.moved(bd.Pos(0,0,z-mb.max.Z)),(0,0,dz))
        back=one(bd.Solid.extrude(face,(0,0,dz)).intersect(
            box((split,-100,b.min.Z-.1),(0,100,b.max.Z+.1))))
        # Continue the mirrored taper into a single level outer header;
        # replacing only the finger would leave the old, narrower header
        # as a rectangular step in the perimeter.
        outer_y=STATIC_JAW_OUTER_SHOULDER_Y_MM
        land=box((split,outer_y,min(z,z+dz)),
                 (b.max.X,b.min.Y+1,max(z,z+dz)))
        back=one(back.fuse(land)).clean()
        if dz<0:
            # Carry the case-facing edge straight to the new bend end,
            # filling the old recessed root corner in the upper cheek.
            root_x=tx+60*math.cos(math.radians(angle))
            patch=box((root_x,-20,z-T),(split+1,STATIC_JAW_WALL_Y_MM,z))
            back=one(back.fuse(patch)).clean()
        # Continue the same outer straight line through the header, until
        # it meets the retained level case shoulder; no step at the split.
        trim=bd.Face(bd.Wire.make_polygon([(split,-100,z),(b.max.X+1,-100,z),
            (b.max.X+1,outer_y_at(b.max.X+1),z),(split,outer_y_at(split),z)],close=True))
        back=one(back.cut(bd.Solid.extrude(trim,(0,0,dz))))
        cheek=one(front.fuse(back)).clean()
        parts.append(cheek)
    result=one(parts[0].fuse(*parts[1:])).clean()
    # Preserve the actual M2 bores where the root/header patch overlaps.
    for face,_ in faces:
        for wire in face.inner_wires():
            result=one(result.cut(bd.Solid.extrude(bd.Face(wire),(0,0,(-T if face.center().Z>b.center().Z else T)))))
    if not result.is_valid:result=result.fix()
    assert result.is_valid and len(result.solids())==1
    result.label=claw.label;result.color=claw.color
    return result


def integrated_camera(frame,upper_plate,*,thickness_mm=T,bend_radius_mm=None,seat_hole_x=None,prepared_foot=False):
    """Continue the upper sheet into the existing Tom camera panel.

    Two bends lift the camera above the wrist; the optical axis points
    toward the jaws at the tom2-specific 25-degree downward pitch.
    """
    T=thickness_mm
    radius=bends.RI if bend_radius_mm is None else bend_radius_mm
    bend=partial(bends.bend,thickness=T,radius=radius)
    bend_end=partial(bends.bend_end,thickness=T,radius=radius)
    straight=partial(bends.straight,thickness=T)
    b=upper_plate.bounding_box()
    width=CAMERA_SUPPORT_WIDTH_MM
    # Centered support: a broad foot leaves 10 mm legs on either side of
    # the casing opening. The opening continues through the first bend.
    if not prepared_foot:
        foot=box((b.max.X-12,-width/2,b.min.Z),(b.max.X,width/2,b.max.Z))
        frame=one(frame.fuse(foot)).clean()
        # Continue the established R11 horn relief into the camera-foot edge,
        # replacing the short right-angle step with one continuous curved edge.
        relief=next(e for e in upper_plate.edges()
                    if e.geom_type==bd.GeomType.CIRCLE and abs(e.radius-11)<1e-6
                    and e.arc_center.Y>0 and abs(e.arc_center.Z-b.max.Z)<1e-5)
        v=max((v.center() for v in relief.vertices()),key=lambda p:p.Y)
        wrap=box((v.X,v.Y,b.min.Z),(b.max.X-12+.01,width/2,b.max.Z))
        relief_cut=bd.Solid.make_cylinder(11,T+.02,
            bd.Plane(origin=(relief.arc_center.X,relief.arc_center.Y,b.min.Z-.01)))
        frame=one(frame.fuse(one(wrap.cut(relief_cut)))).clean()
    mapping=bd.Pos(b.max.X,0,b.max.Z)*bd.Rot(Z=90)
    a0=math.pi;a1=math.radians(CAMERA_RISER_HEADING_DEG)
    a2=math.radians(90-CAMERA_PANEL_PITCH_DEG)
    start=(0,0,0)
    riser_start=bend_end(start,a0,a1)
    riser_end=bends.add(riser_start,bends.direction(a1),CAMERA_RISER_LENGTH_MM)
    panel_start=bend_end(riser_end,a1,a2)
    # Raise the complete pattern clear of the bend die, including the lower
    # cable-tie slot. Only the two free top corners are rounded: the bottom
    # edge joins the bend continuously, without rounded-corner remnants.
    cuts=g.panel_cuts()
    height=g.PANEL_LENGTH+CAMERA_PANEL_BOTTOM_LAND_MM
    outline=bd.Face(bd.Wire.make_polygon([
        (-width/2,0,0),(width/2,0,0),(width/2,height,0),(-width/2,height,0)],close=True))
    outline=outline.fillet_2d(1.0,[v for v in outline.vertices() if v.center().Y>height-.01])
    panel_cuts=[cuts[i] for i in (0,1,2,3,4)]
    # Simple round-ended cable-tie slots replace the clipped-corner slots.
    for x,y,angle in ((-g.TIE_SLOT_X,0,0),(g.TIE_SLOT_X,0,0),
                      (0,-g.TIE_SLOT_X,90),(0,g.TIE_SLOT_X,90)):
        slot=bd.SlotOverall(g.TIE_SLOT_LENGTH,g.TIE_SLOT_WIDTH).rotate(bd.Axis.Z,90+angle)
        panel_cuts.append(slot.moved(bd.Pos(x,g.PANEL_CENTER_S+y,0)))
    panel_cuts=[q.moved(bd.Pos(0,CAMERA_PANEL_BOTTOM_LAND_MM,0)) for q in panel_cuts]
    panel_face=cut_face(outline,panel_cuts)
    panel=bd.extrude(panel_face,amount=T).moved(bends.front_plane(panel_start,a2).location)
    support=one(bend(start,a0,a1,width).fuse(
        straight(riser_start,CAMERA_RISER_LENGTH_MM,a1,width),
        bend(riser_end,a1,a2,width),panel))
    # A continuous developed opening, with R1 ends outside the bend's
    # curved region. Do not subtract a servo-shaped pocket through a bend.
    opening_width=CAMERA_CLEARANCE_WIDTH_MM
    flat=bd.Face(bd.Wire.make_polygon([
        (-opening_width/2,0,0),(opening_width/2,0,0),
        (opening_width/2,CAMERA_CLEARANCE_FLAT_LENGTH_MM,0),
        (-opening_width/2,CAMERA_CLEARANCE_FLAT_LENGTH_MM,0)],close=True))
    flat=flat.fillet_2d(1,[v for v in flat.vertices() if v.center().Y>1])
    flat_cut=bd.Solid.extrude(flat,(0,0,-T))
    riser_face=bd.Face(bd.Wire.make_polygon([
        (-opening_width/2,0,0),(opening_width/2,0,0),
        (opening_width/2,CAMERA_CLEARANCE_RISER_LENGTH_MM,0),
        (-opening_width/2,CAMERA_CLEARANCE_RISER_LENGTH_MM,0)],close=True))
    riser_face=riser_face.fillet_2d(1,[v for v in riser_face.vertices() if v.center().Y>1])
    riser_cut=bd.Solid.extrude(riser_face,(0,0,T)).moved(bends.front_plane(riser_start,a1).location)
    opening=one(flat_cut.fuse(bend(start,a0,a1,opening_width),riser_cut))
    support=support.moved(mapping)
    result=one(frame.fuse(support)).clean()
    result=one(result.cut(opening.moved(mapping))).clean()
    # The enlarged forming land overlaps both existing upper mounting bores.
    for y in (-10.25,10.25):
        result=one(result.cut(bd.Solid.make_cylinder(1.1,T+.02,
            bd.Plane(origin=(SIXTH_NATIVE_ORIGIN[0]-7.25 if seat_hole_x is None else seat_hole_x,y,b.min.Z-.01)))))
    assert result.is_valid and len(result.solids())==1
    result.label=frame.label;result.color=frame.color
    center=bends.add(panel_start,bends.direction(a2),g.PANEL_CENTER_S+CAMERA_PANEL_BOTTOM_LAND_MM)
    optical=bd.Plane(origin=center,x_dir=(1,0,0),z_dir=bends.normal(a2)).location
    payload=camera_payload().moved(g.camera_plane().location.inverse()).moved(optical).moved(mapping)
    payload.label='wrist_camera_payload'
    return result,payload
