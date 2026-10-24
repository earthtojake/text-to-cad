"""F-14D system: airframe — the one-piece blended skin, cut and detailed.

The skin is lofted with certain real openings FILLED (a section through them
is two regions and cannot loft as one wire) and they are cut back here. Which
cutters are applied is decided in THIS file, explicitly:

- KEPT, structural: the boundary-layer diverter slot (`lib/inlets.py`) and the
  cockpit opening under the canopy bubble (`lib/cockpit.py`) — 3 solids, ~348 s.
- DROPPED, cosmetic: the 41 shallow panel recesses `lib/details.py` and
  `lib/aft.py` publish. Measured against this skin the batch did not finish in
  15 minutes and a full 44-cutter build ran over seven hours: the skin is one
  B-spline surface of ~4,900 control points, so every boolean tool forces a
  full-surface classification — the cost is per-tool, not per-unit-of-material.
  Nothing visual is lost: at 19 m rendered to 1920 px a 4 mm groove is
  sub-pixel, and panel lines read from the renderer's feature-edge overlay.

A stage of the aircraft, which `f14d.py` calls in its body: a `@memo`
function, so an edit that does not reach its code replays it from the worker's
memory instead of running it.
"""

from cadgen import memo

from lib import airframe as airframe_lib
from lib import cockpit, inlets


@memo
def airframe():
    cutters = [*inlets.skin_cutters(), *cockpit.skin_cutters()]
    group = airframe_lib.build(cutters)
    return group
