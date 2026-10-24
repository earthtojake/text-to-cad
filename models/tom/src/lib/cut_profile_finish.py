"""Explicit radius corrections for imported cut profiles; no kinematic edits."""


def clearance_root(part, points, direction, root_selector, radius):
    """Expanded rectangular keep-out with only its two root corners rounded."""
    import build123d as b
    from lib.booleans import as_single_shape
    f=b.Face(b.Wire.make_polygon(points,close=True))
    vs=[v for v in f.vertices() if root_selector(v.center())]
    assert len(vs)==2
    f=f.fillet_2d(radius,vs)
    q=as_single_shape(part.cut(b.Solid.extrude(f,direction))).clean()
    assert q.is_valid and len(q.solids())==1 and q.volume<part.volume
    q.label,q.color=part.label,part.color
    return q


