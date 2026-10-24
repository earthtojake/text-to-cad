"""End the upper link's two roll bends at the adjacent connection toe plane."""
import build123d as b
from lib.booleans import as_single_shape as one
from lib.sheet_rule_scs_063 import EFFECTIVE_BEND_RADIUS_MM


def level_roll_bend_ends(part,thickness=1.6):
    """Extend the formed cross-section; keep both bend tangencies and bores.

    The approved flat connection toes establish the axial end plane. The old
    bend ends stopped 0.5 mm short of that plane on each side. Extruding their
    complete native end faces preserves the exact sheet gauge and bend radii.
    """
    xmax=part.bounding_box().max.X
    downward=[f for f in part.faces() if f.geom_type==b.GeomType.PLANE
              and f.normal_at().Z<-.999]
    toes=[f for f in downward if abs(f.bounding_box().max.X-xmax)<1e-4
          and abs(f.bounding_box().size.X-thickness)<1e-4
          and f.bounding_box().size.Y>3]
    assert len(toes)==2,('Upper roll connection toes',len(toes))
    target=toes[0].center().Z
    assert abs(toes[1].center().Z-target)<1e-5
    ends=[f for f in downward if abs(f.bounding_box().max.X-xmax)<1e-4
          and f.bounding_box().size.X>thickness*2
          and any(e.geom_type==b.GeomType.CIRCLE
                  and abs(e.radius-EFFECTIVE_BEND_RADIUS_MM)<1e-5 for e in f.edges())]
    assert len(ends)==2,('Upper roll bend end faces',len(ends))
    lengths=[f.center().Z-target for f in ends]
    assert all(abs(v-.5)<1e-4 for v in lengths),lengths
    extensions=[b.Solid.extrude(f,(0,0,-v)) for f,v in zip(ends,lengths)]
    q=one(part.fuse(*extensions)).clean()
    q.label,q.color=part.label,part.color
    assert q.is_valid and len(q.solids())==1
    return q
