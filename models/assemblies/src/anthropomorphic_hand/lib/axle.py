"""Polished stop-and-ring axles and headless locating dowels, millimeters.

Native axis +Z. Journal datum is Z0..length; a headed axle occupies
-head_thickness..length. A mating bushing bore requires radius+.03 clearance.
The retaining ring groove is centered length-.6, width .32, root radius
radius-.18; filleted groove roots are .04. Rings should have inner radius
radius-.17 (a .01 radial gap), outer radius at most radius+.30 and thickness
.24, centered at length-.6. Head face contact is Z0; concave transition relief
lies INSIDE journal radius, keeping that mating face and bore unobstructed.
Stub lengths 3.5..6 avoid shafts crossing the hand's central tendon corridors.
"""
from math import sqrt
from cadgen import build123d as bd
from .finish import finish


def axle_fit(length=4., radius=1.):
    """Assembly contract, including the free-end groove axial datum."""
    return dict(journal_radius=radius, bore_radius=radius+.03,
                journal_start=0., journal_end=length,
                groove_center=length-.6, groove_width=.32,
                groove_root_radius=radius-.18, groove_root_fillet=.04,
                ring_inner_radius=radius-.17, ring_outer_radius=radius+.30,
                ring_thickness=.24, radial_running_clearance=.03)


def make_axle(length=4., radius=1., head_radius=None, head_thickness=None,
              label="polished_stop_and_ring_axle", neck_radius=None):
    """One lathed, filleted steel body; real hex socket in the head underside.

    Wrist nominal radius3 uses radius4.8 by1.0 head. Larger heads retain the
    same slender dome-edge shoulder language and scale the hex socket to3.0AF.
    Axles are retained by their stop and separate ring, so no threads are used.
    """
    r=float(radius); L=float(length)
    h=float(head_radius if head_radius is not None else (1.8 if r<=1.5 else 4.8))
    t=float(head_thickness if head_thickness is not None else (.6 if r<=1.5 else 1.0))
    if L<2 or r<.7 or h-r<.4 or t<.5:
        raise ValueError("axle needs length>=2, radius>=.7, head overhang>=.4, thickness>=.5")
    edges=[]
    def p(q):return(q[0],0,q[1])
    def line(a,b):edges.append(bd.Edge.make_line(p(a),p(b)))
    def arc(a,m,b):edges.append(bd.Edge.make_three_point_arc(p(a),p(m),p(b)))
    q=.08; d=q/sqrt(2)
    line((0,-t),(h-q,-t))
    arc((h-q,-t),(h-q+d,-t+q-d),(h,-t+q))
    line((h,-t+q),(h,-q))
    arc((h,-q),(h-q+d,-q+d),(h-q,0))
    if neck_radius is None:
        line((h-q,0),(r,0))
        a=.04; d=a/sqrt(2)
        arc((r,0),(r-d,a-d),(r-a,a))
        line((r-a,a),(r-a,.07))
        arc((r-a,.07),(r-d,.07+d),(r,.11))
        journal_begin=.11
    else:
        # A relieved neck below the keyed envelope lets the under-head
        # blend remain round without protruding through the mating D bore.
        neck=float(neck_radius);a=.04;d=a/sqrt(2)
        line((h-q,0),(neck+a,0))
        arc((neck+a,0),(neck+a-d,a-d),(neck,a))
        line((neck,a),(neck,.12))
        edges.append(bd.Edge.make_bezier(p((neck,.12)),p((neck,.28)),p((r,.30)),p((r,.46))))
        journal_begin=.46
    lo=L-.76; hi=L-.44; root=r-.18
    line((r,journal_begin),(r,lo-.02))
    q=.02; d=q/sqrt(2)
    arc((r,lo-.02),(r-q+d,lo-.02+d),(r-q,lo))
    line((r-q,lo),(root+.04,lo))
    q=.04; d=q/sqrt(2)
    arc((root+q,lo),(root+q-d,lo+q-d),(root,lo+q))
    line((root,lo+q),(root,hi-q))
    arc((root,hi-q),(root+q-d,hi-q+d),(root+q,hi))
    line((root+q,hi),(r-.02,hi))
    q=.02;d=q/sqrt(2)
    arc((r-q,hi),(r-q+d,hi+q-d),(r,hi+q))
    line((r,hi+q),(r,L-.05))
    q=.05; d=q/sqrt(2)
    arc((r,L-q),(r-q+d,L-q+d),(r-q,L))
    line((r-q,L),(0,L));line((0,L),(0,-t))
    solid=bd.revolve(bd.Face(bd.Wire(edges)),axis=bd.Axis.Z)
    af=1.3 if r<=1.5 else 3.0
    # Actual six-face socket, opening on exposed head surface, blind in head.
    cutter=bd.Pos(0,0,-t-.01)*bd.extrude(bd.RegularPolygon(af/sqrt(3),6),amount=t*.64+.01)
    solid=solid-cutter
    # Edge-break the exposed socket entrance; leave a deliberate crisp hex.
    entrance=[e for e in solid.edges() if e.geom_type==bd.GeomType.LINE
              and abs(e.center().Z+t)<1e-6 and e.length<af]
    if len(entrance)!=6:
        raise ValueError(f"{label}: expected six socket entrance edges, got {len(entrance)}")
    solid=bd.chamfer(entrance,.035)
    if len(solid.solids())!=1 or not solid.is_valid or solid.volume<=0:
        raise ValueError(f"{label}: axle is not one valid positive solid")
    return finish(solid,"steel",label)


def make_dowel(length=3.5,radius=1.,label="polished_headless_location_dowel"):
    """Headless location pin, +Z0..length, true .05 radiused lead-in at both ends."""
    if length<.3 or radius<.1:raise ValueError("dowel too small for .05 lead-in")
    pin=bd.Cylinder(radius,length,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))
    pin=bd.fillet(pin.edges().filter_by(bd.GeomType.CIRCLE),radius=.05)
    if len(pin.solids())!=1 or not pin.is_valid or pin.volume<=0:
        raise ValueError(f"{label}: dowel is not one valid positive solid")
    return finish(pin,"steel",label)


def driven_axle_fit(length=26., radius=1., flat=.75, journal_bands=(), key_regions=None):
    """Continuous D profile allows withdrawal through every matching D bore."""
    if not .2 < flat < radius or length < 2.:
        raise ValueError("driven axle needs .2 < flat < radius and length >=2")
    if journal_bands or key_regions is not None:
        raise ValueError("Driven shafts require a continuous D section for axial withdrawal")
    out=axle_fit(length,radius)
    out.update(flat_plane_x=flat,key_regions=[(0.,length)],journal_bands=[],
               flat_contact_regions=[(.015,length-.015)],transition_radius=.015,
               key_long_edge_break=.015,minimum_hub_end_clearance=.02)
    return out


def make_driven_axle(length=26., radius=1., flat=.75, journal_bands=(),
                     key_regions=None, head_radius=None, head_thickness=None,
                     label="polished_keyed_driven_axle"):
    """Headed D shaft, including keyed groove and tip, with a real hex socket."""
    driven_axle_fit(length,radius,flat,journal_bands,key_regions)
    solid=make_axle(length,radius,head_radius,head_thickness,label,neck_radius=flat-.10)
    cut=bd.Pos(flat,-radius-1,.05)*bd.Box(radius+1,2*radius+2,length+1,
              align=(bd.Align.MIN,bd.Align.MIN,bd.Align.MIN))
    solid=solid-cut
    # All new edges bound the machined flat, including its groove and tip.
    # A small continuous edge break stays inside the nominal shaft envelope.
    edges=[e for e in solid.edges() if abs(e.bounding_box().min.X-flat)<1e-6
           and abs(e.bounding_box().max.X-flat)<1e-6]
    solid=bd.fillet(edges,.008)
    if len(solid.solids())!=1 or not solid.is_valid or solid.volume<=0:
        raise ValueError(f'{label}: keyed shaft is not one valid positive solid')
    return finish(solid,'steel',label)
