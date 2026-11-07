"""Facts of the panel DXFs for the SendCutSend preflight (no verdicts): units, extents, layers, entity
types, circle diameters, slot widths, the smallest web between cuts and the smallest hole-to-edge distance.
Run: cad run src/check_dxf.py   (the build123d import brings ezdxf; without it `cad run` has none)"""
import math
from collections import Counter
from pathlib import Path

import build123d  # noqa: F401  (ezdxf and shapely arrive with the build123d integration)
import ezdxf
from ezdxf import bbox
from cad.engine.export.dxf import validate_dxf_file
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union, polygonize

OUT = Path(__file__).resolve().parent.parent / "DXF"   # where exports.py writes them
for name in ("twin_orbit_panel_cut.dxf", "twin_orbit_panel_art.dxf"):
    path = OUT / name
    print("==", name)
    for f in validate_dxf_file(path):
        print("  check:", f.render())
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    ext = bbox.extents(msp)
    print("  $INSUNITS", doc.header.get("$INSUNITS"), "extents", tuple(round(v, 3) for v in ext.size)[:2], "mm")
    print("  layers", sorted({e.dxf.layer for e in msp}), "entities", dict(Counter(e.dxftype() for e in msp)))
    if name.endswith("cut.dxf"):
        circles = [e for e in msp.query("CIRCLE")]
        print("  circles (dia mm):", dict(Counter(round(2 * c.dxf.radius, 3) for c in circles)))
        # cut loops -> shapely: outer outline and inner cutouts
        segs = []
        for e in msp:
            t = e.dxftype()
            if t == "LINE":
                segs.append(LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]))
            elif t == "ARC":
                a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
                if a1 < a0:
                    a1 += 2 * math.pi
                n = 24
                c, r = e.dxf.center, e.dxf.radius
                segs.append(LineString([(c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]))
            elif t == "LWPOLYLINE":
                pts = [p[:2] for p in e.get_points()]
                segs.append(LineString(pts + ([pts[0]] if e.closed else [])))
        from shapely import set_precision
        loops = list(polygonize(unary_union([set_precision(s, 1e-3) for s in segs]))) + [Point(c.dxf.center.x, c.dxf.center.y).buffer(c.dxf.radius, 64) for c in circles]
        loops.sort(key=lambda p: -p.area)
        outer, holes = loops[0], loops[1:]
        print(f"  outer {outer.bounds}, {len(holes)} inner cutouts")
        edge = min(outer.exterior.distance(h) for h in holes)
        web = min(a.distance(b) for i, a in enumerate(holes) for b in holes[i + 1:])
        print(f"  smallest hole-to-edge {edge:.3f} mm, smallest web between cutouts {web:.3f} mm")
        slots = [h for h in holes if h.bounds[2] - h.bounds[0] > h.bounds[3] - h.bounds[1] + 0.5]
        for s in slots:
            print(f"  slot {round(s.bounds[2] - s.bounds[0], 3)} x {round(s.bounds[3] - s.bounds[1], 3)} mm at {tuple(round(v, 2) for v in s.centroid.coords[0])}")
