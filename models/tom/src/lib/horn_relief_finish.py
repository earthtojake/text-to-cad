"""R1 cut-profile blends at sharp R11 horn-clearance/straight junctions.

Only thickness-spanning edges are rounded. The functional horn radius,
mounting bores, sheet faces and bend radii are untouched. These convex
material corners lose stock; the servo keep-out is never filled in.
"""
import math
import build123d as b
from lib.corner_rules import SMALL
from lib.servo_case_flange import HORN_CLEARANCE_RADIUS_MM


def sharp_horn_junctions(part):
    result=[]
    for face in part.faces():
        if face.geom_type != b.GeomType.PLANE:
            continue
        normal=face.normal_at()
        lines=[e for e in face.edges() if e.geom_type==b.GeomType.LINE]
        arcs=[e for e in face.edges() if e.geom_type==b.GeomType.CIRCLE
              and abs(e.radius-HORN_CLEARANCE_RADIUS_MM)<1e-5]
        for arc in arcs:
            for point in (arc@0,arc@1):
                tangent=normal.cross(point-arc.arc_center).normalized()
                for line in lines:
                    if min((line@0-point).length,(line@1-point).length)>1e-5:
                        continue
                    # Existing tangent joins (including finished R1 arcs)
                    # require no work. Ignore numerical angular noise.
                    direction=(line@1-line@0).normalized()
                    if abs(tangent.dot(direction))>math.cos(math.radians(.1)):
                        continue
                    for edge in part.edges():
                        if edge.geom_type!=b.GeomType.LINE or not .5<edge.length<6:
                            continue
                        if min((edge@0-point).length,(edge@1-point).length)>1e-5:
                            continue
                        if abs((edge@1-edge@0).normalized().dot(normal))<.999:
                            continue
                        if all((edge.center()-e.center()).length>1e-5 for e in result):
                            result.append(edge)
    return result


def finish_horn_junctions(part):
    edges=sharp_horn_junctions(part)
    if not edges:
        return part
    result=part.fillet(SMALL,edges).clean()
    assert result.is_valid and len(result.solids())==1
    assert result.volume<part.volume, 'Horn-clearance blends must remove stock'
    assert not sharp_horn_junctions(result), 'Unfinished horn-clearance junction'
    result.label,result.color=part.label,part.color
    return result
