"""Remove length only from the solid straight roll-end land of the upper link."""
from dataclasses import asdict
import build123d as b
from lib.mates import revolute
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import box
from lib.corner_rules import SMALL

SHORTENING = 24.29739668901  # Wrist-yoke wall aligns with lower bend end in rest pose.
SECTION_X = 123.0


def motion_map(data, offsets):
    """Add the shorter forearm's one-time translation to wrist descendants."""
    from lib.rest_wrist_contact import wrist_refs
    result=dict(offsets)
    for name in wrist_refs(data):
        assert name in result, ('Missing prior wrist placement',name)
        dx,dy,dz=result[name]
        result[name]=(dx+SHORTENING,dy,dz)
    return result


def revised_kinematics(data):
    mates=[]
    for m in data['mates']:
        r=asdict(m)
        if r['kind']=='revolute' and m.name in ('wristPitch','wristYaw','gripperJaw'):
            xyz=list(r['axis']['origin']);xyz[0]+=SHORTENING
            m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,
                       direction=r['axis']['dir'],limits=r['limits']['value'])
        mates.append(m)
    return data|{'mates':mates}


def clear_roll_notch(part, relief_x, end_level=None):
    """Move the free notch wall without changing the aperture layout or joints."""
    if end_level is None:
        end_level=min(f.center().Z for f in part.faces() if f.geom_type==b.GeomType.PLANE
                      and f.normal_at().Z<-.999 and f.center().X>relief_x+2 and f.area>1)
    q=one(part.cut(box((relief_x,-100,-100),(300,100,end_level)))).clean()
    es=[e for e in q.edges() if e.geom_type==b.GeomType.LINE
        and abs(e.center().X-relief_x)<1e-5 and abs(e.center().Z-end_level)<1e-5
        and abs(e.bounding_box().size.Y-1.6)<1e-5]
    assert len(es)==2,('Link clearance roots',len(es))
    q=q.fillet(SMALL,es).clean()
    q.label,q.color=part.label,part.color
    assert q.is_valid and len(q.solids())==1
    return q


def shorten(part, distance=SHORTENING, *, preserve_roll_relief=False, relief_datum_x=None):
    if not distance:return part
    # Both cuts cross only the constant-height cheeks beyond the diagonal and
    # last opening. The complete perforated channel translates as one part;
    # the wrapped roll-servo mounting return stays on its original datum.
    floor=max((f for f in part.faces() if f.geom_type==b.GeomType.PLANE
               and f.normal_at().Z<-.999 and f.area>1000),key=lambda f:f.area)
    relief_x=floor.bounding_box().max.X
    end_level=min(f.center().Z for f in part.faces() if f.geom_type==b.GeomType.PLANE
                  and f.normal_at().Z<-.999 and f.center().X>relief_x+2 and f.area>1)
    left=one(part.intersect(box((-500,-100,-100),(SECTION_X,100,300))))
    right=one(part.intersect(box((SECTION_X+distance,-100,-100),(500,100,300))))
    q=one(left.moved(b.Pos(distance,0,0)).fuse(right)).clean()
    if preserve_roll_relief:
        if relief_datum_x is not None:
            relief_x=relief_datum_x
        # Shorten the unperforated blank before cutting apertures. Retain the
        # assembly clearance datum unless the profile supplies an aligned one.
        q=clear_roll_notch(q,relief_x,end_level)
    q.label,q.color=part.label,part.color
    assert q.is_valid and len(q.solids())==1
    return q
