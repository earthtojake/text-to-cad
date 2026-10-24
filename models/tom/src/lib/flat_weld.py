"""Weld a flat pattern's panel seams: morphological closing on the developed outline.

WHY THIS EXISTS. Every flat pattern in this repo is assembled from independently projected panels
plus bend-allowance bridges, and the seams between them leave SLIVER NOTCHES in the cut outline --
0.02..0.23 mm wedges at the bend tangents where two panels' edges meet at float precision. The
2026-08-24 SendCutSend preflight found 33 of them across the five order candidates: all below the
laser's kerf, below ALU-080's minimum feature size, and sitting inside die zones. They are drawing
artifacts, not part features; the metal was never going to have them.

WHAT CLOSING DOES, exactly: dilate by EPS then erode by EPS. Convex corners return to themselves
bit-for-bit; concave gaps NARROWER than 2*EPS are filled; concave corners gain a fillet of at most
EPS. At EPS = 0.15 the filled gaps (< 0.30 mm) are all sub-kerf -- the laser could not have cut them
-- and the concave fillet (0.15) is below the kerf radius the cut leaves anyway. Nothing a brake or
a caliper can see changes.

Apply to the finished shapely geometry immediately before it is written to the DXF, never earlier --
the panel booleans upstream rely on exact coordinates.
"""

from __future__ import annotations

WELD_EPS_MM = 0.15


def weld(geometry, eps: float = WELD_EPS_MM):
    """Closing (dilate-erode) that preserves polygon-with-holes structure."""
    from shapely.geometry import Polygon, MultiPolygon

    out = geometry.buffer(eps, resolution=32).buffer(-eps, resolution=32)
    if out.geom_type != geometry.geom_type:
        # closing must not merge or split blanks/holes; if it did, the slivers were not slivers
        raise ValueError(
            f"flat_weld: closing changed the geometry from {geometry.geom_type} to {out.geom_type}; "
            "a gap wider than a sliver was bridged -- inspect instead of welding"
        )
    # Seam repair belongs to the outside contour. Buffering screw holes changes
    # their radii by several microns and replaces exact sampled circle vertices.
    # Retain each original interior ring, so nominal holes export unchanged.
    def restore_holes(original, repaired):
        if len(original.interiors) != len(repaired.interiors):
            raise ValueError("flat_weld changed the hole count")
        result = Polygon(repaired.exterior, original.interiors)
        if not result.is_valid:
            raise ValueError("flat_weld moved an exterior across a preserved hole")
        return result

    if geometry.geom_type == "Polygon":
        return restore_holes(geometry, out)
    remaining = list(out.geoms)
    repaired_parts = []
    for original in geometry.geoms:
        match = max(remaining, key=lambda p: p.intersection(original).area)
        remaining.remove(match)
        repaired_parts.append(restore_holes(original, match))
    return MultiPolygon(repaired_parts)
