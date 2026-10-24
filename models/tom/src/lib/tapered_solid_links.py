"""Solid parallel-taper links with a compact four-hole shoulder connection.

The root keeps the sketched 11 mm drop. Straight landing lengths solve a
shared diagonal after lowering the elbow; mounting patterns remain intact.
Stock and all existing bend radii remain 2.032 mm / R0.9652.
"""
import math
import build123d as b
from lib.corner_rules import SMALL
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify
from lib.elbow_roll_alignment import CASE_EDGE_ALIGNMENT_EXTRA

T=2.032
ROOT_DROP=11.0
ROOT_STRAIGHT=8.0
SCREW_EDGE_LAND=2.65
RELIEF_HEIGHT=15.5
RELIEF_R=SMALL
# The root mounting flange ends flush with the measured servo-case back.
# The longitudinal bend begins after that flat mounting flange, rising above it.
SHOULDER_CASE_BACK_Z = 97.912576694501
COMPACT_DROP = 101.96051104553 - SHOULDER_CASE_BACK_Z
REMOVED_SHOULDER_SCREWS = {'pitch_case_m2x6_2', 'pitch_case_m2x6_4'}
BEND_END_CLEARANCE = 2.0
FLANGE_CORNER_R = SMALL
# The negative-Y wire bay ends at X=-36.5624 in the shoulder datum.
SHOULDER_WIRE_BAY_END_X = -36.5624
WIRE_EDGE_CLEARANCE = 1.0
# Align the visible wrist screw column with the upright shoulder column in Rest.
WRIST_INSET = -36.9124 - (-38.9597766945)
# Transfer equal length between links: in Rest the wrist travels twice this
# amount, putting its back-wall face on the shoulder case's outer X plane.
LINK_TRANSFER = (-59.5249766945 - (-84.2276)) / 2
UPPER_SHORTEN = WRIST_INSET + LINK_TRANSFER
# Raised-cover envelope controls clearance beneath the upper mounting tab.
SERVO_FEATURE_GAP = 0.5
RAISED_COVER_TOP_Z = 92.503085422377


def shorten_upper_blank(p):
    """Remove a slice from the filled channel, carrying its wrist end inward."""
    left=one(p.intersect(box(-300,0,-100,100,-100,300)))
    right=one(p.intersect(box(UPPER_SHORTEN,300,-100,100,-100,300)))
    return finish(left.moved(b.Pos(UPPER_SHORTEN,0,0)).fuse(right),p)


def compact_lower_fold(p, rows, old_tangent):
    root=[xyz for axis,xyz in rows if axis=='Y' and xyz[0]<0]
    x=max(q[0] for q in root)
    distal=[xyz for axis,xyz in rows if axis=='Y' and xyz[0]>50]
    start=x+1.1+BEND_END_CLEARANCE
    stop=min(q[0] for q in distal)-1.1-BEND_END_CLEARANCE
    tangent=old_tangent-COMPACT_DROP
    roof=one(p.intersect(box(start,stop,-40,40,old_tangent,200))).moved(b.Pos(0,0,-COMPACT_DROP))
    walls=one(p.cut(box(-100,200,-40,40,old_tangent,200),
                    box(-100,x-SCREW_EDGE_LAND,-40,40,0,200),
                    box(start,200,-40,40,tangent,200)))
    # Trim the ENTIRE wall thickness: bore coordinates are midplanes, not
    # side-face coordinates. Both flat tabs share the servo-case-back datum.
    walls=one(walls.cut(box(x-SCREW_EDGE_LAND-.1,start,-40,40,tangent,200)))
    # Continuous rail on the selected raised-panel side. The 2 mm screw
    # center-to-edge land keeps this straight rail clear of the case boss.
    y=max(q[1] for q in root)
    z0=min(q[2] for q in root)-SCREW_EDGE_LAND
    walls=one(walls.cut(box(-100,x-2.0,y-T/2-.1,y+T/2+.1,z0,tangent+.1)))
    walls=one(walls.fuse(box(x-2.0,start,y-T/2,y+T/2,z0,tangent)))
    return finish(drill_mounts(walls.fuse(roof),[r for r in rows if r[1][0]>-50]),p)


def box(x0,x1,y0,y1,z0,z1):
    return b.Solid.make_box(x1-x0,y1-y0,z1-z0,b.Plane(origin=(x0,y0,z0)))


def prism(points,y0,y1):
    f=b.Face(b.Wire.make_polygon([(x,y0,z) for x,z in points],close=True))
    return b.Solid.extrude(f,(0,y1-y0,0))


def finish(p,original):
    p=_unify(one(p).clean())
    assert p.is_valid and len(p.solids())==1,original.label
    p.label,p.color=original.label,original.color
    return p


def round_flange_corners(p):
    """Round exposed outline corners through the stock, retaining formed bends."""
    edges=[]
    solid=p.solids()[0]
    faces=p.faces()
    for e in p.edges():
        bb=e.bounding_box()
        if e.geom_type!=b.GeomType.LINE or abs(e.length-T)>1e-5:continue
        if max(bb.size)<T-1e-5:continue
        adjacent=[f for f in faces if any(e==other for other in f.edges())]
        if len(adjacent)!=2 or any(f.geom_type!=b.GeomType.PLANE for f in adjacent):continue
        n1,n2=[f.normal_at() for f in adjacent]
        if abs(n1.dot(n2))>.999:continue
        # A mixed inward/outward probe is inside at a reentrant corner.
        # Keep those junctions intact rather than adding material near a servo.
        if solid.is_inside(e.center()+(n1-n2)*.05):continue
        edges.append(e)
    assert edges, p.label
    result=p.fillet(FLANGE_CORNER_R,edges)
    assert result.volume<p.volume
    return finish(result,p)


def fill_patterns(p):
    plugs=[]
    for f in p.faces():
        if f.geom_type!=b.GeomType.PLANE:continue
        n=f.normal_at()
        if max(n.Y,n.Z)<.99:continue
        for w in f.inner_wires():
            if max(w.bounding_box().size)<2.3:continue
            plugs.append(b.Solid.extrude(b.Face(w),tuple(-T*v for v in n)))
    return finish(p.fuse(*plugs),p) if plugs else p


def side_faces(p):
    return sorted((f for f in p.faces() if f.geom_type==b.GeomType.PLANE
        and f.normal_at().Y>.99 and f.area>1500),key=lambda f:f.center().Y)


def mount_bores(p):
    rows=[]
    for f in p.faces():
        if f.geom_type!=b.GeomType.CYLINDER or abs(f.radius-1.1)>1e-5:continue
        bb=f.bounding_box()
        axis='Y' if abs(bb.size.Y-T)<1e-5 else 'X' if abs(bb.size.X-T)<1e-5 else None
        if axis:rows.append((axis,tuple(bb.center())))
    return rows


def drill_mounts(p,rows):
    tools=[]
    for axis,xyz in rows:
        q=list(xyz);i=0 if axis=='X' else 1;q[i]-=T/2+.1
        direction=(1,0,0) if axis=='X' else (0,1,0)
        tools.append(b.Solid.make_cylinder(1.1,T+.2,b.Plane(origin=q,z_dir=direction)))
    return one(p.cut(*tools))


def case_relief(p,rows,*,right):
    # Only the raised-panel side needs an opening; the other rail stays solid.
    bores=[xyz for axis,xyz in rows if axis=='Y' and xyz[1]>0]
    end=max(x[0] for x in bores) if right else min(x[0] for x in bores)
    pair=[x for x in bores if abs(x[0]-end)<1e-5]
    assert len(pair)==2
    z=sum(q[2] for q in pair)/2;y=pair[0][1]
    extra=RELIEF_R-.8  # Extend root to preserve the original case keep-out.
    xa,xb=(end-6-extra,end+30) if right else (end-30,end+6+extra)
    f=b.Face(b.Wire.make_polygon([(xa,y-T,z-RELIEF_HEIGHT/2),(xb,y-T,z-RELIEF_HEIGHT/2),
        (xb,y-T,z+RELIEF_HEIGHT/2),(xa,y-T,z+RELIEF_HEIGHT/2)],close=True))
    f=f.fillet_2d(RELIEF_R,f.vertices())
    return one(p.cut(b.Solid.extrude(f,(0,2*T,0))))


def shoulder_case_relief(p,rows):
    # The upright root case has the same raised panel, rotated 90 degrees.
    # Leave the opposite wall intact, as at the other case interfaces.
    bores=[xyz for axis,xyz in rows if axis=='Y' and xyz[1]>0 and xyz[0]<0]
    z=max(q[2] for q in bores)
    pair=[q for q in bores if abs(q[2]-z)<1e-5]
    assert len(pair)==2
    x=sum(q[0] for q in pair)/2;y=pair[0][1]
    f=b.Face(b.Wire.make_polygon([(x-RELIEF_HEIGHT/2,y-T,z-30),
        (x+RELIEF_HEIGHT/2,y-T,z-30),(x+RELIEF_HEIGHT/2,y-T,z+6+RELIEF_R-.8),
        (x-RELIEF_HEIGHT/2,y-T,z+6+RELIEF_R-.8)],close=True))
    f=f.fillet_2d(RELIEF_R,f.vertices())
    return one(p.cut(b.Solid.extrude(f,(0,2*T,0))))


def extend_fold(p,old_end,new_end,tangent,upper):
    if abs(new_end-old_end)<1e-6:return p
    caps=[f for f in p.faces() if f.geom_type==b.GeomType.PLANE
          and f.normal_at().X>.99 and abs(f.bounding_box().min.X-old_end)<1e-5
          and abs(f.bounding_box().max.X-old_end)<1e-5
          and (f.bounding_box().max.Z<=tangent+1e-5 if upper else f.bounding_box().min.Z>=tangent-1e-5)]
    assert len(caps)>=1,(p.label,len(caps))
    return one(p.fuse(*[b.Solid.extrude(f,(new_end-old_end,0,0)) for f in caps]))


def tapered_links(lower,upper,lower_case,upper_case):
    lower_bores=mount_bores(lower)
    # The source lower channel still carries the legacy elbow bores.
    lower_bores=[(a,(q[0]+(LINK_TRANSFER if q[0]>50 else 0),q[1],q[2]-COMPACT_DROP if q[0]>50 else q[2])) for a,q in lower_bores]
    upper_bores=mount_bores(upper)
    upper_bores=[(a,(q[0]+(UPPER_SHORTEN if a=='Y' else 0),q[1],q[2]+CASE_EDGE_ALIGNMENT_EXTRA if a=='Y' else q[2])) for a,q in upper_bores]
    # Existing small bores must be filled before moving their centers.
    def plug_bores(p):
        plugs=[]
        for axis,q in mount_bores(p):
            xyz=list(q);i=0 if axis=='X' else 1;xyz[i]-=T/2
            plugs.append(b.Solid.make_cylinder(1.1001,T,b.Plane(origin=xyz,z_dir=(1,0,0) if i==0 else (0,1,0))))
        return finish(p.fuse(*plugs),p)
    lo,up=fill_patterns(plug_bores(lower)),fill_patterns(plug_bores(upper))
    from lib.reach600_geometry import extend_blank
    lo=finish(extend_blank(lo,amount=LINK_TRANSFER),lower)
    up=shorten_upper_blank(up)
    sides=side_faces(lo);assert len(sides)==2
    # Root ledge remains outside the shoulder case; only its depth changes.
    root_x=lo.bounding_box().min.X+28.9597766945
    root_z=68.3-ROOT_DROP
    taper_start=root_x+ROOT_STRAIGHT
    distal=[xyz for axis,xyz in lower_bores if axis=='Y' and xyz[0]>50]
    distal_x=max(q[0] for q in distal)
    case_box=lower_case.bounding_box()
    # The diagonal meets the full rectangular case-mounting block at the
    # case back, not at either side's different screw-tab endpoint.
    diagonal_end=case_box.min.X
    distal_z=case_box.min.Z
    slope=(distal_z-root_z)/(diagonal_end-taper_start)
    # With the elbow lowered, solve the root straight landing as well as
    # the upper tip landing. Keep at least 8 mm at the formed roll end.
    upper_sides=side_faces(up)
    upper_top=max(f.bounding_box().max.Z for f in upper_sides)
    upper_right=max(f.bounding_box().max.X for f in upper_sides)
    wrist_rows=[xyz for axis,xyz in upper_bores if axis=='Y']
    wrist_box=upper_case.bounding_box()
    upper_start=wrist_box.max.X
    upper_start_z=wrist_box.max.Z
    slope=max(slope,(upper_top-upper_start_z)/(upper_right-8.0-upper_start))
    taper_start=diagonal_end-(distal_z-root_z)/slope
    tangent=sides[0].bounding_box().max.Z
    roof=max((f for f in lo.faces() if f.geom_type==b.GeomType.PLANE and f.normal_at().Z>.99),key=lambda f:f.area)
    old_end=roof.bounding_box().max.X
    # User's e451: the shorter mounting tab ends on the negative-Y side.
    end=min(f.bounding_box().max.X for f in sides)
    lo=extend_fold(lo,old_end,end,tangent,False)
    for f in sides:
        bb=f.bounding_box();y=f.center().Y
        lo=one(lo.fuse(box(root_x,bb.max.X,y-T,y,root_z,tangent)))
    # Both diagonals stop at the case back; both tabs finish horizontally.
    taper_end_z=distal_z
    lo=one(lo.cut(prism([(taper_start,root_z),(diagonal_end,taper_end_z),
                         (500,taper_end_z),(500,-500),(taper_start,-500)],-30,30)))
    lo=case_relief(drill_mounts(lo,lower_bores),lower_bores,right=True)
    lo=shoulder_case_relief(lo,lower_bores)
    lo=finish(lo,lower)
    lo=compact_lower_fold(lo,lower_bores,tangent)

    sides=side_faces(up);assert len(sides)==2
    tangent=min(f.bounding_box().min.Z for f in sides)
    top=max(f.bounding_box().max.Z for f in sides)
    xright=max(f.bounding_box().max.X for f in sides)
    wrist=[xyz for axis,xyz in upper_bores if axis=='Y']
    xstart=wrist_box.max.X
    zstart=wrist_box.max.Z
    knee=xstart+(top-zstart)/slope
    # End the filled elbow recess directly below the tangent point of the
    # rounded diagonal-to-horizontal transition (the selected top edge).
    upper_fold_end=knee+FLANGE_CORNER_R*math.tan(math.atan(slope)/2)
    assert xright-knee>2.5,'Upper straight tip must retain a useful bend landing'
    case_rows=[xyz for axis,xyz in upper_bores if axis=='X']
    ledge=min(q[2] for q in case_rows)-2.3
    # The upper blank already carries the elbow translation; its roll-end
    # fold terminates at the same distal station as the extended lower link.
    up=extend_fold(up,old_end,upper_fold_end,tangent,True)
    for f in sides:
        bb=f.bounding_box();y=f.center().Y
        # Fill both old diagonals before cutting the new shared profile.
        up=one(up.fuse(box(bb.min.X,xright,y-T,y,tangent,top)))
    up=one(up.cut(prism([(-100,zstart),(xstart,zstart),(knee,top),
                        (knee,500),(-100,500)],-30,30)))
    up=one(up.cut(box(upper_fold_end,xright+50,-30,30,-500,ledge)))
    up=case_relief(drill_mounts(up,upper_bores),upper_bores,right=False)
    up=finish(up,upper)
    # Match the wrist's rectangular case block and begin its fold after
    # the mounting column, mirroring the lower link's elbow connection.
    # Both folds start after their own mounting columns; their distal ends
    # share the elbow station after redistributing length between the links.
    root_rows=[q for a,q in lower_bores if a=='Y' and q[0]<0]
    start=max(q[0] for q in root_rows)+1.1+BEND_END_CLEARANCE
    upper_fold_start=max(q[0] for q in wrist_rows)+1.1+BEND_END_CLEARANCE
    stop=min(q[0] for q in distal)-1.1-BEND_END_CLEARANCE
    up=one(up.cut(box(upper_fold_end,xright+50,-40,40,-100,ledge)))
    up=one(up.cut(box(-100,upper_fold_start,-40,40,-100,tangent)))
    if wrist_box.min.Z<tangent:
        for f in sides:
            y=f.center().Y
            up=one(up.fuse(box(f.bounding_box().min.X,upper_fold_start,y-T,y,wrist_box.min.Z,tangent+.1)))
    else:
        up=one(up.cut(box(-100,upper_fold_start,-40,40,-100,wrist_box.min.Z)))
    up=finish(drill_mounts(up,upper_bores),upper)
    # Bring the flush-side root wall toward the servo while leaving a full
    # millimeter beyond the measured cable-bay envelope.
    lo=finish(lo.fuse(box(SHOULDER_WIRE_BAY_END_X+WIRE_EDGE_CLEARANCE,
                         -33.9123,-19.032,-17.0,73.75,92.9)),lo)
    # One straight cut between the tabs; no extra rail projecting over the
    # raised cover. Retain the 0.5 mm gap under the upper mounting tab.
    lo=finish(lo.cut(box(-60,SHOULDER_WIRE_BAY_END_X+WIRE_EDGE_CLEARANCE,-19.132,-16.9,
                        92.9,RAISED_COVER_TOP_Z+SERVO_FEATURE_GAP)),lo)
    # Preserve the rounded root tabs and their screw-edge lands.
    root_flange_x=max(q[0] for q in root_rows)-2.15
    lo=finish(lo.cut(box(-100,root_flange_x,-19.132,-16.9,root_z-.1,
                        SHOULDER_CASE_BACK_Z+.1)),lo)
    lo,up=round_flange_corners(lo),round_flange_corners(up)
    return lo,up,dict(slope=slope,lower_root_z_mm=root_z,lower_straight_mm=taper_start-root_x,
                     upper_straight_mm=xright-knee,fold_end_x_mm=end,fold_extension_mm=end-old_end,
                     elbow_drop_mm=COMPACT_DROP,
                     lower_taper_end_x_mm=diagonal_end,lower_taper_end_z_mm=taper_end_z,
                     lower_bend_start_x_mm=start,upper_bend_start_x_mm=upper_fold_start,bend_end_x_mm=stop,
                     lower_bend_length_mm=stop-start,upper_bend_end_x_mm=upper_fold_end,
                     upper_bend_length_mm=upper_fold_end-upper_fold_start,
                     link_transfer_mm=LINK_TRANSFER,flange_corner_radius_mm=FLANGE_CORNER_R,
                     wire_edge_clearance_mm=WIRE_EDGE_CLEARANCE,wrist_inset_mm=WRIST_INSET,
                     servo_feature_gap_mm=SERVO_FEATURE_GAP)


def apply_tapered_links(assembly):
    link_names={'shoulder_pitch_yoke','elbow_roll_link_plate_pair'}
    names=link_names|{'elbow_pitch_servo','wrist_pitch_servo'};world={}
    def collect(p,ancestor=None):
        if ancestor is None:ancestor=b.Location()
        if p.label in names:
            q=b.Compound.cast(p.wrapped).moved(ancestor);q.label,q.color=p.label,p.color;world[p.label]=q
        for c in p.children:collect(c,ancestor*p.location)
    collect(assembly)
    lo,up,dimensions=tapered_links(world['shoulder_pitch_yoke'],world['elbow_roll_link_plate_pair'],
                                  world['elbow_pitch_servo'],world['wrist_pitch_servo'])
    print('Solid tapered links:',dimensions,flush=True)
    replacements={p.label:p for p in (lo,up)}
    def affected(p):return p.label in link_names or any(affected(c) for c in p.children)
    def visit(p,ancestor=None):
        if ancestor is None:ancestor=b.Location()
        if p.label in replacements:return replacements[p.label].moved(ancestor.inverse())
        if p.children and affected(p):
            loc,cs,label,color=p.location,list(p.children),p.label,p.color;p.children=()
            return b.Compound(children=[visit(c,ancestor*loc) for c in cs],label=label,color=color).moved(loc)
        return p
    return visit(assembly)
