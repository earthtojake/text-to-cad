"""Align the sideways elbow case top with the lower link's sidewall edge.

The wrist and perforated forearm stay put. Raise the elbow pitch servo on
the lower link and carry the original, unmodified yoke with it. The roll
servo and forearm case-mounting end follow. Sheet gauge is retained.
"""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify

# First establish the wrist-centerline layout, then lift the whole elbow
# another 0.555423 mm so its casing top reaches the selected link edge.
# Measured on the saved STEP: case top Z101.4050877400365, edge Z101.96051104553.
CASE_EDGE_ALIGNMENT_EXTRA = 0.555423305494
ROLL_RISE = 10.772288347277 + CASE_EDGE_ALIGNMENT_EXTRA


def box(x0, x1, y0, y1, z0, z1):
    return bd.Solid.make_box(x1-x0, y1-y0, z1-z0,
                             bd.Plane(origin=(x0, y0, z0)))


def finish(shape, original):
    result = _unify(one(shape).clean())
    assert result.is_valid and len(result.solids()) == 1
    result.label, result.color = original.label, original.color
    return result


def raise_case_mount(part, rise=ROLL_RISE):
    # This unperforated land is beyond the last truss node and floor end.
    # Move the complete case flanges and their bends; join each sidewall
    # with a ruled, constant-gauge transition across a 10 mm land.
    end = part.bounding_box().max.X
    x0, x1 = end-24.5, end-14.5
    left = one(part.intersect(box(-500, x0, -500, 500, -500, 500)))
    right = one(part.intersect(box(x1, 500, -500, 500, -500, 500)))
    right = right.moved(bd.Pos(0, 0, rise))
    def caps(shape, x):
        return sorted((f for f in shape.faces()
                       if abs(f.bounding_box().min.X-x) < 1e-5
                       and abs(f.bounding_box().max.X-x) < 1e-5),
                      key=lambda f: f.center().Y)
    a, b = caps(left, x0), caps(right, x1)
    assert len(a) == len(b) == 2, 'Transition must cross two solid sidewalls'
    bridges = [bd.Solid.make_loft([fa.outer_wire(), fb.outer_wire()], ruled=True)
               for fa, fb in zip(a, b)]
    return finish(left.fuse(right, *bridges), part)


def raise_pitch_case_holes(part, rise=ROLL_RISE):
    """Lift S3's four side bores, filling the old diagonal above its tabs."""
    sides = [f for f in part.faces() if f.geom_type == bd.GeomType.PLANE
             and f.normal_at().Y > .99 and f.area > 2000]
    assert len(sides) == 2
    additions = []
    for f in sides:
        slope = [e for e in f.outer_wire().edges() if e.geom_type == bd.GeomType.LINE
                 and e.bounding_box().min.X > 80 and e.bounding_box().size.X > 5
                 and e.bounding_box().size.Z > 5]
        assert len(slope) == 1
        edge = slope[0]
        a, c = sorted((edge.start_point(),edge.end_point()),key=lambda v:v.X)
        right = f.bounding_box().max.X
        y = f.center().Y
        outline = bd.Wire.make_polygon([(a.X,y,a.Z),(c.X,y,c.Z),
                                        (right,y,c.Z),(right,y,a.Z)],close=True)
        additions.append(bd.Solid.extrude(bd.Face(outline),(0,-2.032,0)))
    bores = []
    for f in part.faces():
        if f.geom_type == bd.GeomType.CYLINDER and abs(f.radius-1.1) < 1e-5:
            bb = f.bounding_box()
            if bb.center().X > 90 and abs(bb.size.Y-2.032) < 1e-5:
                bores.append((bb.center().X,bb.min.Y,bb.center().Z))
    assert len(bores) == 4
    for x,y,z in bores:
        additions.append(bd.Solid.make_cylinder(1.1001,2.032,
                         bd.Plane(origin=(x,y,z),z_dir=(0,1,0))))
    p = one(part.fuse(*additions)).clean()
    cutters = [bd.Solid.make_cylinder(1.1,4.032,
               bd.Plane(origin=(x,y-1,z+rise),z_dir=(0,1,0))) for x,y,z in bores]
    return restore_pitch_case_reliefs(finish(p.cut(*cutters),part))


def restore_pitch_case_reliefs(part):
    """Open both case-mount rails between their M2 screws for the case boss.

    The 14 mm raised servo panel gets a 15.5 mm high opening with R0.8
    internal corners. The two 20.5 mm-pitch mounting holes stay intact.
    """
    bores = [f.bounding_box() for f in part.faces()
             if f.geom_type == bd.GeomType.CYLINDER and abs(f.radius-1.1)<1e-5
             and f.bounding_box().center().X>90
             and abs(f.bounding_box().size.Y-2.032)<1e-5]
    assert len(bores)==4
    cutters=[]
    for y in sorted({round(bb.min.Y,6) for bb in bores}):
        pair=[bb.center() for bb in bores if abs(bb.min.Y-y)<1e-5]
        assert len(pair)==2
        x=pair[0].X-6
        z=sum(c.Z for c in pair)/2
        face=bd.Face(bd.Wire.make_polygon([(x,y-1,z-7.75),(x+30,y-1,z-7.75),
            (x+30,y-1,z+7.75),(x,y-1,z+7.75)],close=True))
        face=face.fillet_2d(.8,face.vertices())
        cutters.append(bd.Solid.extrude(face,(0,4.032,0)))
    return finish(part.cut(*cutters),part)


def align_elbow_roll(assembly, rise=ROLL_RISE):
    world = {}
    names = {'elbow_pitch_yoke', 'elbow_roll_link_plate_pair','shoulder_pitch_yoke'}
    def collect(p, ancestor=bd.Location()):
        if p.label in names:
            q = bd.Compound.cast(p.wrapped).moved(ancestor)
            q.label, q.color = p.label, p.color
            world[p.label] = q
        for c in p.children:
            collect(c, ancestor*p.location)
    collect(assembly)
    replacements = {
        'elbow_pitch_yoke': world['elbow_pitch_yoke'].moved(bd.Pos(0,0,rise)),
        'elbow_roll_link_plate_pair': raise_case_mount(world['elbow_roll_link_plate_pair'], rise),
        'shoulder_pitch_yoke': raise_pitch_case_holes(world['shoulder_pitch_yoke'],rise),
    }
    moving = {'elbow_roll_servo','elbow_pitch_servo','elbow_yoke_horn_screws',
              'elbow_roll__hex_socket_m3x5__center','elbow_pitch__hex_socket_m3x5__center'}
    moving.update(f'elbow_side_m2x6_{i}' for i in range(1,5))
    moving.update(f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02}'
                  for i in (1, 2, 7, 8))
    targets = names | moving
    def affected(p):
        return p.label in targets or any(affected(c) for c in p.children)
    def visit(p, ancestor=bd.Location()):
        if p.label in replacements:
            return replacements[p.label].moved(ancestor.inverse())
        if p.label in moving:
            return p.moved(ancestor.inverse()*bd.Pos(0, 0, rise)*ancestor)
        if p.children and affected(p):
            # Reparenting children can reset the old compound's location.
            # Capture it first and retain unrelated subassemblies intact.
            loc, children, label, color = p.location, list(p.children), p.label, p.color
            p.children=()
            return bd.Compound(children=[visit(c, ancestor*loc) for c in children],
                               label=label, color=color).moved(loc)
        return p
    return visit(assembly)
