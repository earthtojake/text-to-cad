"""600 mm study: extended channels, registered Howe lattice, steel clamp.

Clamp stock: 6.35 mm HRPO A36 steel; R3.81 bends (SCS .250 table).
Four 2.2 mm M2 bores are final drilled dimensions, not qualified laser holes.
"""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib import link_truss as tr

LINK_EXTENSION=37.5
CLAMP_T=6.35
CLAMP_R=3.81
POST_HEIGHT=25.0
ARM_RISE=CLAMP_T+POST_HEIGHT-(3.175+10.0)
MOUNT_XY=((-9.2,9.75),(11.5,9.75),(-9.2,-10.75),(11.5,-10.75))


def extend_blank(part,amount=LINK_EXTENSION,station=30.0):
    left=one(part.intersect(bd.Solid.make_box(station+500,1000,1000,bd.Plane(origin=(-500,-500,-500)))))
    right=one(part.intersect(bd.Solid.make_box(500-station,1000,1000,bd.Plane(origin=(station,-500,-500)))))
    caps=[f for f in left.faces() if f.geom_type==bd.GeomType.PLANE and abs(f.center().X-station)<1e-6 and abs(f.normal_at().X)>.999]
    assert caps
    fills=[bd.Solid.extrude(f,(amount,0,0)) for f in caps]
    result=one(left.fuse(*fills,right.moved(bd.Pos(amount,0,0)))).clean()
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result


def finish_extended_link(part,upper):
    from lib.howe_link_pattern import finish_blank
    blank=extend_blank(tr.finish_link(part,upper,pattern=False))
    return finish_blank(blank,upper)
