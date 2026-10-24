"""ALU-063 bend correction while holding both adjoining sheet planes fixed.

5052-H32 0.063-inch stock: R0.889 mm, K=0.42, verified 2026-10-10
against SendCutSend's official specifications. Existing links use the rounded
nominal 1.6 mm stock dimension (0.0002 mm below the catalog value).
"""
import math
import build123d as b
from lib.booleans import as_single_shape as one
from lib.sheet_rule_scs_063 import EFFECTIVE_BEND_RADIUS_MM, K_FACTOR


def correct_link_bends(part, thickness=1.6, old_radius=.9652):
    """Replace complete quarter bends; no seating plane, bore or joint moves."""
    new_radius=EFFECTIVE_BEND_RADIUS_MM
    delta=old_radius-new_radius
    assert delta>0
    bend_faces=[f for f in part.faces() if f.geom_type==b.GeomType.CYLINDER
                and abs(f.radius-old_radius)<1e-6]
    assert len(bend_faces) in (2,4),len(bend_faces)
    result=part
    for f in bend_faces:
        arcs=[e for e in f.edges() if e.geom_type==b.GeomType.CIRCLE]
        assert len(arcs)==2
        c0,c1=[e.arc_center for e in arcs]
        axis=c1-c0
        # Input STEP endpoints carry nanometre-scale residuals: analytic bends
        # are orthogonal to the assembly axes, so recover their exact directions.
        def unit(v):return b.Vector(*(round(x) for x in v.normalized()))
        u,v=[unit(vertex.center()-c0) for vertex in arcs[0].vertices()]
        assert abs(u.dot(v))<1e-9 and abs(u.dot(axis.normalized()))<1e-6
        ro=old_radius+thickness; rn=new_radius; rno=rn+thickness
        nc=c0+(u+v)*delta
        a=c0+u*ro; aa=nc+u*rno; bb=nc+v*rno; cc=c0+v*ro
        dd=c0+v*old_radius; ee=nc+v*rn; ff=nc+u*rn; gg=c0+u*old_radius
        outer=b.Edge.make_three_point_arc(aa,nc+(u+v)*(rno/math.sqrt(2)),bb)
        inner=b.Edge.make_three_point_arc(ee,nc+(u+v)*(rn/math.sqrt(2)),ff)
        wire=b.Wire([b.Edge.make_line(a,aa),outer,b.Edge.make_line(bb,cc),
                     b.Edge.make_line(cc,dd),b.Edge.make_line(dd,ee),inner,
                     b.Edge.make_line(ff,gg),b.Edge.make_line(gg,a)])
        replacement=b.Solid.extrude(b.Face(wire),axis)
        cell=b.Solid.extrude(b.Face(b.Wire.make_polygon([c0,c0+u*ro,c0+(u+v)*ro,c0+v*ro],close=True)),axis)
        result=one(result.cut(cell).fuse(replacement)).clean()
        assert result.is_valid and len(result.solids())==1
    result.label,result.color=part.label,part.color
    return result
