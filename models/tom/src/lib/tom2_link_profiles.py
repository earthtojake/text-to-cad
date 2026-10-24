"""Solid link panels with servo mounting bores, for the compact bend study."""
import build123d as bd
from lib.booleans import as_single_shape as one

from lib.tom2_dimensions import LINK_ROOF_HEIGHT_MM

ROOT_LAND_EXTENSION_MM = 19.0  # Existing outer-profile knee; independent of openings.


def _face(points, y):
    return bd.Face(bd.Wire.make_polygon([(x,y,z) for x,z in points],close=True))


def _unify(shape):
    # The pinned assembly carries nearly coplanar surfaces separated by
    # sub-micron import tolerances. Explicit tolerances merge those surfaces
    # without retaining the old opening outlines as internal face seams.
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.ShapeFix import ShapeFix_Shape
    solid=one(shape)
    fix=ShapeFix_Shape(solid.wrapped)
    fix.SetPrecision(1e-6)
    fix.SetMaxTolerance(1e-5)
    fix.Perform()
    unify=ShapeUpgrade_UnifySameDomain(fix.Shape(),True,True,True)
    unify.SetLinearTolerance(1e-5)
    unify.SetAngularTolerance(1e-5)
    unify.Build()
    result=bd.Solid(unify.Shape())
    assert result.is_valid and abs(result.volume-solid.volume)<.001
    return result


def fill_access_openings(body):
    plugs=[]
    for f in body.faces():
        if f.geom_type!=bd.GeomType.PLANE:continue
        n=f.normal_at()
        if max(n.X,n.Y,n.Z)<.999:continue
        for w in f.inner_wires():
            dims=sorted(w.bounding_box().size)
            if dims[-1]<4:continue  # Servo mounting holes remain.
            # All remaining access holes are internal to broad flat stock.
            # A small overlap avoids imported coincident-edge tolerances.
            bb=w.bounding_box();lo=list(bb.min);hi=list(bb.max)
            axis=max(range(3),key=lambda i:list(n)[i])
            lo[axis]-=2.032
            for i in range(3):
                if i!=axis:lo[i]-=.001;hi[i]+=.001
            plugs.append(bd.Solid.make_box(*(hi[i]-lo[i] for i in range(3)),
                         bd.Plane(origin=lo)))
    result=one(body.fuse(*plugs)).clean() if plugs else body
    assert result.is_valid and len(result.solids())==1
    return result


def resize_rest_links(parts, *, shoulder_web_x):
    """Reuse formed stock, close access openings and retain mounting patterns."""
    by_label={p.label:p for p in parts}
    upper=by_label['elbow_roll_link_plate_pair'].solids()[0]
    lower=by_label['shoulder_pitch_yoke'].solids()[0]
    servo=by_label['elbow_roll_servo']
    wall=max((f for f in upper.faces() if f.geom_type==bd.GeomType.PLANE
        and f.normal_at().Y>.999),key=lambda f:f.area)
    slope_edge=max((e for e in wall.outer_wire().edges()
        if e.geom_type==bd.GeomType.LINE and abs(e.start_point().Z-e.end_point().Z)>1
        and abs(e.start_point().X-e.end_point().X)>1),key=lambda e:e.length)
    start,end=sorted((slope_edge.start_point(),slope_edge.end_point()),key=lambda p:p.X)
    lower_edge=max((e for e in lower.edges() if e.geom_type==bd.GeomType.LINE
        and abs(e.start_point().X-e.end_point().X)>100
        and abs(e.start_point().Z-e.end_point().Z)>10),key=lambda e:e.length)
    lower_end=max((lower_edge.start_point(),lower_edge.end_point()),key=lambda p:p.X)
    fold_z=upper.bounding_box().min.Z
    fold_x=(start.X+lower_end.X)/2
    fold=bd.Axis((fold_x,0,fold_z),(0,1,0))
    target_z=servo.bounding_box().max.Z
    knee_x=end.X-ROOT_LAND_EXTENSION_MM
    old_faces=[bd.Face(w) for w in wall.inner_wires() if w.bounding_box().size.Z>10]
    y0=upper.bounding_box().min.Y
    y1=upper.bounding_box().max.Y
    gauge=2.032
    def fill(body,faces):
        plugs=[]
        for f in faces:
            b=f.bounding_box()
            for y in (y0,y1-gauge):
                # Overlap the slot edges inside the existing wall. Matching
                # imported rounded edges exactly leaves tolerance-sized seams.
                plugs.append(bd.Solid.make_box(b.size.X+.002,gauge,b.size.Z+.002,
                    bd.Plane(origin=(b.min.X-.001,y,b.min.Z-.001))))
        result=one(body.fuse(*plugs))
        expected=sum(f.area for f in faces)*2*gauge
        assert abs(result.volume-body.volume-expected)<.01, 'Slot fill changed the outer profile'
        return result
    upper=fill(upper,old_faces)
    # Reauthor the lower flats as single profiles. The historical lower
    # channel contains many fused patches with inconsistent planar curves;
    # preserving those patches also preserves obsolete cutout seam edges.
    tangent=2*fold_z-(upper.bounding_box().min.Z+2.9972)
    low_knee=2*fold_x-knee_x
    root_x=-51.5
    root_z=fold_z-LINK_ROOF_HEIGHT_MM
    # Rest directly on the level top of the stationary horn bracket.
    # The shallow taper retains the original distal mounting envelope.
    from lib.elbow_yoke_integration import PITCH_TOP
    low_z=root_z+PITCH_TOP
    side_inner=(y0+gauge,y1-gauge)
    # Build the uninterrupted roof and its bends directly. Filling historical
    # roof slots otherwise retains coincident planar seam loops in the STEP.
    roof_left=lower.bounding_box().min.X
    roof_right=max(f.bounding_box().max.X for f in lower.faces()
        if f.geom_type==bd.GeomType.PLANE and f.normal_at().Z>.999
        and abs(f.center().Z-fold_z)<1e-5)
    ri=.9652;ro=ri+gauge
    cy0=side_inner[0]+ri;cy1=side_inner[1]-ri
    roof_pieces=[bd.Solid.make_box(roof_right-roof_left,cy1-cy0,gauge,
        bd.Plane(origin=(roof_left,cy0,fold_z-gauge)))]
    for cy,sign in ((cy0,-1),(cy1,1)):
        pl=bd.Plane(origin=(roof_left,cy,tangent),z_dir=(1,0,0))
        ring=bd.Solid.make_cylinder(ro,roof_right-roof_left,pl).cut(
            bd.Solid.make_cylinder(ri,roof_right-roof_left,pl))
        ya=min(cy,cy+sign*ro)
        clip=bd.Solid.make_box(roof_right-roof_left,ro,ro,
            bd.Plane(origin=(roof_left,ya,tangent)))
        roof_pieces.append(one(ring.intersect(clip)))
    roof=one(roof_pieces[0].fuse(*roof_pieces[1:])).clean()
    panels=[]
    front_end_bridges=[]
    for y,sign,far,ear_length in ((side_inner[0],-1,32.75,7.51),(side_inner[1],1,29,11.76)):
        left=root_x-13.25
        right=lower_end.X+ear_length
        window_x=lower_end.X+2
        ear_top=fold_z-9
        ear_bottom=fold_z-25
        tip=root_z+far-2.65
        root_strip=[(root_x+8,low_z)]
        # Solid rail across each former servo access notch; keep the mounting
        # hole positions while removing the old window-height constraint.
        root_strip += [(root_x+8,root_z+10.95),(root_x+13.25,root_z+10.95),
                       (root_x+13.25,tip),(left,tip)]
        points=[(left,tangent),(right,tangent)]
        # Close the corresponding distal access notch on both upper sheets.
        bridge_face=_face([(window_x-.01,ear_bottom-1.001),
            (right,ear_bottom-1.001),(right,ear_top+1.001),
            (window_x-.01,ear_top+1.001)],y)
        front_end_bridges.append(bd.Solid.extrude(bridge_face,(0,sign*gauge,0)).rotate(fold,180))
        points += [(right,lower_end.Z),(lower_end.X,lower_end.Z),
            (low_knee,low_z)]
        points += root_strip
        f=_face(points,y)
        rounded=[(right,z) for z in (tangent,lower_end.Z)]+[(left,tip)]
        rounded += [(root_x+8,root_z+10.95)]
        vs=[v for v in f.vertices() if any(abs(v.center().X-x)<1e-5 and
            abs(v.center().Z-z)<1e-5 for x,z in rounded)]
        f=f.fillet_2d(1,vs)
        panel=bd.Solid.extrude(f,(0,sign*gauge,0))
        bores=set()
        for e in lower.edges():
            if e.geom_type==bd.GeomType.CIRCLE and abs(e.radius-1.1)<1e-6 and abs(e.arc_center.Y-y)<1e-5:
                bores.add((round(e.arc_center.X,8),round(e.arc_center.Z,8)))
        assert len(bores)==5
        tools=[bd.Solid.make_cylinder(1.1,gauge+.02,bd.Plane(
            origin=(x,y-sign*.01,z),z_dir=(0,sign,0))) for x,z in bores]
        tools.append(bd.Solid.make_cylinder(11,gauge+.02,bd.Plane(
            origin=(root_x,y-sign*.01,root_z),z_dir=(0,sign,0))))
        panels.append(one(panel.cut(*tools)))
    lower=one(roof.fuse(*panels)).clean()
    cut=_face([(start.X,start.Z),(knee_x,target_z),(1000,target_z),
               (1000,1000),(start.X,1000)],-40)
    cutter=bd.Solid.extrude(cut,(0,80,0))
    upper=one(upper.cut(cutter))
    upper=_unify(one(upper.fuse(*front_end_bridges)))
    # Fill enclosed roof/side lightening apertures, keeping all small round
    # mounting bores. These are flat-stock plugs, never whole-part scaling.
    upper=fill_access_openings(upper)
    lower=fill_access_openings(lower)
    replacements={}
    for label,q in (('elbow_roll_link_plate_pair',upper),('shoulder_pitch_yoke',lower)):
        assert q.is_valid and len(q.solids())==1,label
        q.label=label;q.color=by_label[label].color
        replacements[label]=q
    return [replacements.get(p.label,p) for p in parts]
