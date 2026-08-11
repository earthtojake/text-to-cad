"""The F-14D airframe skin: one lofted solid, nose to nozzles.

This is the piece the whole aeroplane hangs off.  It is a SINGLE multi-section
loft through the blended sections in ``sections.py`` -- forebody, gloves,
inlets, nacelles and the pancake tunnel are one surface, not separate bodies
fused together.  Nothing here is filleted, because there is nothing to fillet:
the transitions come out of the section maths already continuous.
"""

from __future__ import annotations

import math

from build123d import (Axis, Face, Location, Plane, Solid, Spline, Vector,
                       Vertex, Wire, loft)

from f14_parts import geometry as G
from f14_parts import sections as SEC


def _wire_at(x, n=52):
    """Closed section wire at station x, as two splines meeting at the two
    lateral silhouette corners."""
    top, bot = SEC.section_curves(x, n)
    if len(top) < 4:
        return None
    tp = [Vector(x, y, z) for y, z in top]
    bp = [Vector(x, y, z) for y, z in bot]
    upper = Spline(*tp)
    lower = Spline(*bp)
    return Wire([upper.edge(), lower.edge()])


def skin_sections(n=52, stations=None):
    """Every section wire, plus the nose vertex, in loft order."""
    xs = stations if stations is not None else SEC.stations()
    out = [Vertex(0.0, 0.0, SEC.surfaces(0.0, 0.0)[0])]
    for x in xs:
        if x <= 1e-6:
            continue
        w = _wire_at(x, n)
        if w is not None:
            out.append(w)
    return out


def build_skin(n=52, ruled=False):
    """The airframe skin as one solid."""
    secs = skin_sections(n)
    faces = [s if isinstance(s, Vertex) else Face(s) for s in secs]
    return loft(faces, ruled=ruled)


if __name__ == "__main__":
    import time

    t0 = time.time()
    xs = SEC.stations()
    print(f"{len(xs)} stations")
    solid = build_skin()
    t1 = time.time()
    bb = solid.bounding_box()
    print(f"loft   {t1-t0:6.2f}s")
    print(f"volume {solid.volume/1e9:8.3f} m^3")
    print(f"bbox   x {bb.min.X/G.M:7.3f}..{bb.max.X/G.M:7.3f}  "
          f"y {bb.min.Y/G.M:7.3f}..{bb.max.Y/G.M:7.3f}  "
          f"z {bb.min.Z/G.M:7.3f}..{bb.max.Z/G.M:7.3f}")
    print(f"faces {len(solid.faces())}  valid {solid.is_valid()}")
