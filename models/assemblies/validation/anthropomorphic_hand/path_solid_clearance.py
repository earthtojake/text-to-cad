"""Verify a reported path contact with a boundary-distance separation proof.

OCCT has classified an endpoint outside a solid's exact bounding box as inside.
For a connected wire, positive distance from every boundary face plus one
outside-box vertex proves that the entire wire lies outside the solid. This
does not ignore small overlaps: a wire entering material meets the boundary.
"""
from cadgen import build123d as bd


def boundary_separation(wire, solid, radius):
    assert len(wire.wires()) == 1 and wire.is_valid, 'The outside-witness proof requires one valid connected wire'
    assert solid.solids(), 'Clearance requires a solid body'
    box = solid.bounding_box()
    outside = next((tuple(v.center()) for v in wire.vertices()
                    if any(p < lo-1e-6 or p > hi+1e-6
                           for p, lo, hi in zip(v.center(), box.min, box.max))), None)
    if outside is None:
        return {'proven_separated': False, 'reason': 'no outside-box witness'}
    boundary = bd.Compound(children=list(solid.faces()))
    assert not boundary.solids() and boundary.faces()
    distance = wire.distance_to(boundary)
    return {'proven_separated': distance > radius+1e-6,
            'method': 'connected wire separated from all boundary faces with outside-box vertex',
            'outside_vertex_mm': outside,
            'solid_bounds_mm': [tuple(box.min), tuple(box.max)],
            'boundary_distance_mm': distance,
            'surface_gap_lower_bound_mm': distance-radius-1e-6}
