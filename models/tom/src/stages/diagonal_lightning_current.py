"""Long-diagonal lightning alternative at the current arm's exact rest datums.

The references are immutable current-arm BREP checkpoints.  These plates retain
all formed folds and mounting datums; only free side-wall contours and lightening
apertures change.  The matched lower diagonal needs extra shoulder-side depth;
its floor meets the base carrier without relocating any joint.
"""
from pathlib import Path
import math
import build123d as b
from lib.booleans import as_single_shape as one
from lib.corner_rules import SMALL, MEDIUM, LARGE, XL, XXL
from lib.tapered_solid_links import box, prism, finish
from lib.tapered_link_patterns import offset, clip, face, section
from lib.m2_connection_rollout import revise_part, LOWER, UPPER
from lib.scs_link_bends import correct_link_bends
from lib.upper_roll_return import level_roll_bend_ends
from lib.stacked_link_contact import extend_bend_section
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'STEP/imported/recovered/narrow_truss'
T=1.6
RAIL=6.0
SLOT_WIDTH=8.0
SLOT_PITCH=15.0
TOP_LAND=30.0
LOWER_FLOOR=49.65


def fill_openings(p):
    tools=[]
    for f in p.faces():
        if f.geom_type!=b.GeomType.PLANE:continue
        n=f.normal_at()
        if max(n.Y,n.Z)<.99:continue
        for w in f.inner_wires():
            if b.Face(w).area<6:continue
            tools.append(b.Solid.extrude(b.Face(w),tuple(-T*v for v in n)))
    return finish(p.fuse(*tools),p)


def sides(p):
    return [f for f in p.faces() if f.geom_type==b.GeomType.PLANE and f.normal_at().Y>.99 and f.area>1500]


def round_at(p, points):
    for x,z,r in points:
        es=[e for e in p.edges() if e.geom_type==b.GeomType.LINE and abs(e.length-T)<1e-4
            and abs(e.bounding_box().size.Y-T)<1e-4 and abs(e.center().X-x)<1e-4 and abs(e.center().Z-z)<1e-4]
        if not es:raise ValueError(('Missing prescribed corner',x,z,r))
        p=finish(p.fillet(r,es),p)
    return p


def blank_links(lower_floor=LOWER_FLOOR,*,lower_root=-20.775):
    lo,up=[fill_openings(revise_part(b.import_brep(str(BASE/(n+'.brep'))),specs)) for n,specs in [('o1.8',LOWER),('o1.14',UPPER)]]
    # Analytic case/bend bounds from the current rest assembly.  The long
    # upper diagonal starts exactly at the wrist-case crossing, and terminates
    # 30 mm before the vertical roll-wall tangency.
    x_start=1.727756699993
    z_start=132.100153389
    x_end=128.25502779367-TOP_LAND
    z_end=154.850153389
    for _ in range(10):
        slope=(z_end-z_start)/(x_end-x_start)
        x_end=128.25502779367-TOP_LAND-SMALL*math.tan(math.atan(slope)/2)
    slope=(z_end-z_start)/(x_end-x_start)
    # Replace only the upper two side-wall roofs. Preserve all stock below the
    # wrist-case top and the roll flange itself; there are no kinematic changes.
    for f in sides(up):
        y=f.center().Y;xmax=f.bounding_box().max.X
        up=one(up.fuse(box(x_start,xmax,y-T,y,z_start-.01,z_end)))
        up=one(up.cut(prism([(-100,z_start),(x_start,z_start),(x_end,z_end),(x_end,300),(-100,300)],y-T-.00001,y+.00001)))
    up=finish(up,lo)
    # The shallow convex diagonal/flat knees use the approved XXL/R20 on
    # both cheeks. Concave roots retain XL/R4; compact apertures retain R1.
    up=round_at(up,[(x_start,z_start,XL),(x_end,z_end,XXL)])
    # Preserve the approved end-block floor. Additional material extends toward
    # the shoulder while the matched diagonal runs to the distal case crossing.
    lower_end=111.63965119917;lower_z=70.65
    lower_start=lower_end-(lower_z-lower_floor)/slope
    root=lower_root  # Flush with the locked shoulder-yoke web's +X face in rest pose.
    for f in sides(lo):
        y=f.center().Y
        profile=[(root,lower_floor),(lower_start,lower_floor),(lower_end,lower_z),(lower_end,lower_z+.01),(root,lower_z+.01)]
        lo=one(lo.fuse(prism(profile,y-T,y)))
    lo=finish(lo,up)
    lo=round_at(lo,[(root,lower_floor,MEDIUM),(lower_start,lower_floor,XXL)])
    # The recessed distal connection's R1 root and the diagonal used to leave
    # a 0.0134 mm² enclosed pinhole at their join. Fill that residual region;
    # it is neither a mounting hole nor a lightening aperture.
    plugs=[]
    for f in sides(lo):
        for w in f.inner_wires():
            if b.Face(w).area<.1 and 110<w.center().X<112 and 70<w.center().Z<71:
                plugs.append(b.Solid.extrude(b.Face(w),(0,-T,0)))
    if plugs:lo=finish(lo.fuse(*plugs),lo)
    lo,up=[correct_link_bends(p,T) for p in (lo,up)]
    up=level_roll_bend_ends(up,T)
    # World-coordinate profiles accepted in the connection inspection. Their
    # bores, seating planes and join direction are identical to the current arm.
    # Approved connection contours were applied before the wall reprofiling.
    lo.label='diagonal_lightning_lower';up.label='diagonal_lightning_upper'
    return [lo,up],dict(slope=slope,lower_knee=lower_start,upper_knee=x_start,upper_end=x_end)


def make_diagonal_links(lower_floor=LOWER_FLOOR,*,lower_root=-20.775,upper_rise=0.0,upper_shortening=0.0,toe_clearance=0.8,align_upper_relief=False,extra_upper_wrist_opening=False,extra_upper_web_opening=False,pattern_shift_x=0.0,upper_relief_x=None):
    blanks,dimensions=blank_links(lower_floor,lower_root=lower_root);slope=dimensions['slope']
    blanks[1]=extend_bend_section(blanks[1],upper_rise)
    if upper_shortening:
        from lib.forearm_roll_flip import extend_return
        from lib.forearm_shortening import shorten
        blanks[1]=shorten(extend_return(blanks[1],toe_clearance=toe_clearance),
                          upper_shortening,preserve_roll_relief=True,
                          # Align the lower relief with the virtual sharp
                          # diagonal/flat intersection, not its arc tangent.
                          relief_datum_x=(dimensions['upper_end']+upper_shortening
                                          if align_upper_relief else None))
    reference=102.8277766945
    # The lower distal connection has a recessed R1 root at x=111.002 mm.
    # Its safe envelope is x=111.0, not the wider diagonal/case crossing.
    # This keeps the last slot 6 mm from that rounded connection as well.
    upper_start=1.727756699993+upper_shortening
    upper_end=dimensions['upper_end']+upper_shortening
    upper_right=120.34624504707
    # A shorter forearm can put the diagonal-to-flat knee beyond the floor's
    # elbow relief. Clip the aperture domain to the actual diagonal there;
    # a backwards roof edge would make the inset polygon self-intersect.
    upper_roof=[(upper_right,154.850153389),(upper_end,154.850153389)] if upper_end<upper_right else [
        (upper_right,132.100153389+slope*(upper_right-upper_start))]
    domains=[
      [(-19.5,lower_floor),(dimensions['lower_knee'],lower_floor),(111.0,70.65-slope*(111.63965119917-111.0)),(111.0,100.2625766945),(-19.5,100.2625766945)],
      [(upper_start,105.3929766945-upper_rise),(upper_right,105.3929766945-upper_rise),*upper_roof,(upper_start,132.100153389)]
    ]
    flats=[]
    for p in blanks:
        f=max((f for f in p.faces() if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        flats.append(f.bounding_box())
    ymin=max(bb.min.Y for bb in flats);ymax=min(bb.max.Y for bb in flats)
    half=SLOT_WIDTH*math.hypot(1,slope)/2
    # Each sloping side slot belongs to one station in world rest coordinates.
    # Its flat-web slot has the same station at the common web contact plane.
    limits=[]
    for i,(poly,bb) in enumerate(zip(domains,flats)):
        dz=upper_rise if i else 0.0
        inset=offset(poly,RAIL)
        left=min(x for x,z in inset);right=max(x for x,z in inset)
        a=max(left+slope*(z+dz-reference) for z in section(inset,left))+half
        c=min(right+slope*(z+dz-reference) for z in section(inset,right))-half
        limits.append((max(a,bb.min.X+RAIL+half),min(c,bb.max.X-RAIL-half)))
    a,c=limits[1];c=min(v[1] for v in limits)
    count=int((c-a)//SLOT_PITCH)+1
    anchor=c-(count-1)*SLOT_PITCH
    result=[]
    for i,(p,poly,bb,(a,c)) in enumerate(zip(blanks,domains,flats,limits)):
        stations=[anchor+j*SLOT_PITCH for j in range(math.ceil((a-anchor)/SLOT_PITCH-1e-8),math.floor((c-anchor)/SLOT_PITCH+1e-8)+1)]
        inset=offset(poly,RAIL);side=[];flat=[]
        extra_station=None
        if i==1 and (extra_upper_wrist_opening or extra_upper_web_opening):
            extra_station=stations[0]-SLOT_PITCH
            stations.insert(0,extra_station)
            # The real wrist connection extends beyond the conservative
            # rectangular end of the aperture domain. Continue one full slot
            # into that land, preserving the diagonal and top/bottom rails.
            extended=list(poly)
            extended[0]=(poly[0][0]-SLOT_PITCH,poly[0][1])
            extended[-1]=(poly[-1][0]-SLOT_PITCH,poly[-1][1]-slope*SLOT_PITCH)
            end_inset=offset(extended,RAIL)
        local_reference=reference-(upper_rise if i else 0.0)
        roof=[(bb.min.X+RAIL,ymin+RAIL),(bb.max.X-RAIL,ymin+RAIL),(bb.max.X-RAIL,ymax-RAIL),(bb.min.X+RAIL,ymax-RAIL)]
        for x in stations:
            domain=end_inset if x==extra_station else inset
            q=clip(clip(domain,1,slope,x+slope*local_reference+half),-1,-slope,-x-slope*local_reference+half)
            if x!=extra_station or extra_upper_wrist_opening:
                side.append(face(q,SMALL))
            # The end web opening retains the full repeated width. Its left
            # land may be less than RAIL, but the slot must remain contained.
            web_domain=roof
            if x==extra_station:
                assert x-half>bb.min.X+T, 'End web opening has insufficient edge land'
                web_domain=[(bb.min.X,ymin+RAIL),(bb.max.X-RAIL,ymin+RAIL),
                            (bb.max.X-RAIL,ymax-RAIL),(bb.min.X,ymax-RAIL)]
            q=clip(clip(web_domain,1,0,x+half),-1,0,-x+half)
            flat.append(face(q,SMALL))
        # Shift finished apertures rigidly: preserve their corner radii, width,
        # height and pitch without clipping a new corner at a diagonal knee.
        if pattern_shift_x:
            side=[f.moved(b.Pos(pattern_shift_x,0,0)) for f in side]
            flat=[f.moved(b.Pos(pattern_shift_x,0,0)) for f in flat]
            stations=[x+pattern_shift_x for x in stations]
        cutters=[b.Solid.extrude(f.rotate(b.Axis.X,90).moved(b.Pos(0,25,0)),(0,-50,0)) for f in side]
        cutters += [b.Solid.extrude(f.moved(b.Pos(0,0,bb.min.Z-T-.05)),(0,0,2*T+.1)) for f in flat]
        q=finish(p.cut(*cutters),p)
        if i==1 and upper_relief_x is not None:
            from lib.forearm_shortening import clear_roll_notch
            q=clear_roll_notch(q,upper_relief_x)
        result.append(q)
        print(q.label,dict(stations=stations,apertures=len(side),volume_mm3=q.volume,matched_slope=slope,top_land_mm=TOP_LAND,lower_floor_mm=lower_floor),flush=True)
    return result


def diagonal_lightning_current():
    return b.Compound(children=make_diagonal_links(),label='diagonal_lightning_current')
