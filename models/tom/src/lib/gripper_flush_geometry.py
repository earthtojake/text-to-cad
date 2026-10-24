"""Shared fixed-jaw edge and matching tip geometry for the current arm.

The flat-side connection toe is also the fixed jaw's bend tangent. Servo
mounts and joint angles remain fixed; the moving finger length is solved from
its existing direction, and the fixed finger ends at their intersection.
"""
import build123d as b
from lib.short_gripper_trial import datums,box
from lib.gripper_063 import RADIUS,THICKNESS
from lib.m2_connection_profiles import FLAT_END_TOE
from lib.booleans import as_single_shape as one

FIXED_FOLD_Y=-12.225+FLAT_END_TOE


def dimensions(stock):
    parts={}
    def collect(p,a):
        loc=a*p.location
        if p.label in ('servo6_fixed_gripper_frame','gripper_right_claw'):
            parts[p.label]=b.Compound.cast(p.wrapped.Moved(a.wrapped))
        for c in p.children:collect(c,loc)
    collect(stock,b.Location())
    _,tip,_,_,_=datums(parts['servo6_fixed_gripper_frame'],False)
    _,_,_,direction,moving_length=datums(parts['gripper_right_claw'],True)
    shift=FIXED_FOLD_Y+RADIUS+THICKNESS-tip.Y
    assert direction.Y>.1,'Moving finger must converge on the fixed jaw'
    moving_extension=-shift/direction.Y
    return dict(shift=shift,moving_extension=moving_extension,
                fixed_extension=moving_extension*direction.X,
                contact_length=moving_length+moving_extension,
                outer_y=-24.0238+shift)


def finish_header(part):
    """Continue the straight upper flat-side toe into the finger bend.

    Only the planar header is trimmed. The adjacent curved bend surface and
    lower cleared-side connection remain intact, as do all mounting bores.
    """
    from lib.gripper_connection_finish import UPPER,LOWER,T
    root=datums(part,False)[2].X
    # Reconstruct the complete straight toe, including the half-millimetre
    # seam between the old connection coupons. This strip ends before the
    # existing M2 bore envelopes and does not enter either bend.
    rail=box((root,FIXED_FOLD_Y-1,UPPER),(-107.835,FIXED_FOLD_Y,UPPER+T))
    q=one(part.fuse(rail)).clean()
    from lib.corner_rules import SMALL
    upper_cut=b.Face(b.Wire.make_polygon([(root,FIXED_FOLD_Y,UPPER-.00001),
        (-106.835,FIXED_FOLD_Y,UPPER-.00001),(-106.835,3,UPPER-.00001),
        (root,3,UPPER-.00001)],close=True))
    upper_cut=upper_cut.fillet_2d(SMALL,[v for v in upper_cut.vertices()
        if abs(v.X+106.835)<1e-5 and abs(v.Y-FIXED_FOLD_Y)<1e-5])
    q=one(q.cut(b.Solid.extrude(upper_cut,(0,0,T+.00002)))).clean()
    # The opposing sheet has the same straight jaw tangent. Extend its
    # adjacent land to that datum rather than leaving the cropped old wedge.
    q=one(q.cut(box((root,FIXED_FOLD_Y,LOWER-.00001),
                   (-132.335,3,LOWER+T+.00001)))).clean()
    # Smooth the two convex straight-to-horn transitions. These rounds
    # remove stock only, retaining the complete functional horn keep-out.
    from lib.gripper_connection_finish import _at_corner
    q=_at_corner(q,-110.877,12.215683782645,UPPER)
    q=_at_corner(q,-110.413,12.642080743785,LOWER)
    # Imported planar edges differ by minute angular noise. Join their
    # collinear segments without widening the kernel's linear tolerance:
    # a larger linear tolerance can erase short edges and invalidate a bend.
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    unify=ShapeUpgrade_UnifySameDomain(q.wrapped,True,True,True)
    unify.SetLinearTolerance(1e-7)
    unify.SetAngularTolerance(1e-6)
    unify.AllowInternalEdges(False)
    unify.Build()
    q=one(b.Compound.cast(unify.Shape()))
    q.label,q.color=part.label,part.color
    assert q.is_valid and len(q.solids())==1
    return q
