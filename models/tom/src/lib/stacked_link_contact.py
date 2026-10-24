"""Extend the upper channel depth without moving any joint or mounting hole."""
import build123d as b
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import box


def extend_bend_section(part,depth,thickness=1.6):
    if not depth:return part
    # Split through straight cheeks just above the formed floor. The complete
    # existing floor/bends translate together, preserving their radii and gauge.
    floor=min(f.center().Z for f in part.faces() if f.geom_type==b.GeomType.PLANE
              and f.normal_at().Z<-.999 and f.area>1000)
    from lib.sheet_rule_scs_063 import EFFECTIVE_BEND_RADIUS_MM
    split=floor+thickness+EFFECTIVE_BEND_RADIUS_MM+.15
    cell=box((-500,-100,-500),(500,100,split))
    bottom=one(part.intersect(cell));walls=one(part.cut(cell))
    ends=[f for f in walls.faces() if f.geom_type==b.GeomType.PLANE
          and abs(f.center().Z-split)<1e-5 and f.normal_at().Z<-.999]
    assert len(ends)==2,('Upper channel straight-wall sections',len(ends))
    extensions=[b.Solid.extrude(f,(0,0,-depth)) for f in ends]
    q=one(walls.fuse(bottom.moved(b.Pos(0,0,-depth)),*extensions)).clean()
    q.label,q.color=part.label,part.color
    assert q.is_valid and len(q.solids())==1
    return q
