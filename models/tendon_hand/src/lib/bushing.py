"""Turned miniature flanged joint bushings; dimensions in millimeters.

Native axis is +Z. The sleeve occupies 0..length; the flange is outward at
length..length+flange_thickness. Default OD 5.00 in the phalanx's 5.06 bore
leaves .03 radial clearance. ID 2.06 leaves .03 radial running clearance
around a 2.00 shaft. For opposed eyes, rotate the second bushing 180 degrees
about X and place each flange against its own eye's OUTER face. Never put
both flanges between eyes. No interference fit is asserted: retain with the
shaft shoulder and external retainer; leave .04 axial shaft end float.

The flange's seating face is Z=length. Its tiny root relief lies INSIDE the
sleeve OD, so the seating transition cannot intersect a close fitting eye.
"""

from math import sqrt
from cadgen import build123d as bd
from .finish import finish


def make_bushing(outer_radius=2.50, bore_radius=1.03, length=1.45,
                 flange_radius=2.75, flange_thickness=.18,
                 label="polished_joint_bushing"):
    """One closed lathed solid with rounded lips and a recessed face ring.

    Wrist family: outer_radius=5, bore_radius=3.03, length=3,
    flange_radius=5.45, flange_thickness=.28. Dimensions describe finished
    cylindrical surfaces; the .06 lead-in chamfers do not reduce bearing
    engagement elsewhere. This is a plain bushing, not a cosmetic bearing.
    """
    if not (0 < bore_radius < outer_radius < flange_radius):
        raise ValueError("bushing radii must obey 0 < bore < outer < flange")
    if length < .4 or flange_thickness < .16:
        raise ValueError("bushing length or flange thickness too small for lips")
    if outer_radius-bore_radius < .5 or flange_radius-outer_radius < .20:
        raise ValueError("bushing needs .5 wall and .20 flange overhang")
    r, b, f, t, L = outer_radius,bore_radius,flange_radius,flange_thickness,length
    z = L+t
    lip=.06
    d=lip/sqrt(2)
    edges=[]
    def p(q): return (q[0],0,q[1])
    def line(a,c): edges.append(bd.Edge.make_line(p(a),p(c)))
    def arc(a,m,c): edges.append(bd.Edge.make_three_point_arc(p(a),p(m),p(c)))
    # Bore lead-ins have a straight .06 x .06 miniature chamfer.
    line((b,.06),(b,z-.06))
    line((b,z-.06),(b+.06,z))
    # The turned recess is a smooth-bottom annular channel on the outward face.
    ring=b+(f-b)*.64
    line((b+.06,z),(ring-.12,z))
    a=.02/sqrt(2)
    arc((ring-.12,z),(ring-.12+a,z-.02+a),(ring-.10,z-.02))
    arc((ring-.10,z-.02),(ring-.08-a,z-.02-a),(ring-.08,z-.04))
    line((ring-.08,z-.04),(ring+.08,z-.04))
    arc((ring+.08,z-.04),(ring+.08+a,z-.02-a),(ring+.10,z-.02))
    arc((ring+.10,z-.02),(ring+.12-a,z-.02+a),(ring+.12,z))
    line((ring+.12,z),(f-lip,z))
    arc((f-lip,z),(f-lip+d,z-lip+d),(f,z-lip))
    line((f,z-lip),(f,L+lip))
    arc((f,L+lip),(f-lip+d,L+lip-d),(f-lip,L))
    line((f-lip,L),(r,L))
    # Tangent concave relief entirely within OD; face contact remains planar.
    line((r,L),(r-.02,L))
    arc((r-.02,L),(r-.02-a,L-.02+a),(r-.04,L-.02))
    line((r-.04,L-.02),(r-.04,L-.04))
    arc((r-.04,L-.04),(r-.02-a,L-.04-a),(r-.02,L-.06))
    arc((r-.02,L-.06),(r-.02+a,L-.08+a),(r,L-.08))
    line((r,L-.08),(r,.06))
    line((r,.06),(r-.06,0))
    line((r-.06,0),(b+.06,0))
    line((b+.06,0),(b,.06))
    solid=bd.revolve(bd.Face(bd.Wire(edges)),axis=bd.Axis.Z)
    if len(solid.solids()) != 1 or not solid.is_valid or solid.volume <= 0:
        raise ValueError(f"{label}: bushing profile is not one valid positive solid")
    return finish(solid,"steel",label)
