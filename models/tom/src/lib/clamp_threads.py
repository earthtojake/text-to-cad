"""M3 x 0.5 right-hand internal threads for the assembly/inspection clamp.

Nominal 60-degree thread form, 3 mm major diameter, P/8 root flats,
truncated at the selected 2.6 mm tap-pilot diameter. This visual solid is
not a thread tolerance gauge. The manufacturing export uses the same
clamp factory before tapping, with four 2.6 mm bores, and specifies the
M3 x 0.5 tapping service separately.
"""
from math import sqrt, ceil
import build123d as b
from lib.base_direct_clamp import CLAMP_T, ATTACH_XY
from lib.booleans import as_single_shape as one
from lib.materials import ALUMINUM_5052_COLOR

THREAD_PITCH = 0.5
THREAD_MAJOR_RADIUS = 1.5
THREAD_PILOT_RADIUS = 1.3


def thread_cutter():
    pitch = THREAD_PITCH
    z = -pitch/2
    inner = THREAD_PILOT_RADIUS-0.03  # overlap the open pilot for a clean Boolean
    outer = THREAD_MAJOR_RADIUS
    root_half = pitch/16
    inner_half = root_half+(outer-inner)/sqrt(3)
    profile = b.Face(b.Wire.make_polygon([
        (inner,0,z-inner_half), (outer,0,z-root_half),
        (outer,0,z+root_half), (inner,0,z+inner_half)], close=True))
    helix = b.Helix(pitch, pitch, THREAD_PILOT_RADIUS,
                    center=(0,0,z), lefthand=False)
    return b.Solid.sweep(profile, helix, is_frenet=True)


def tap_clamp(p):
    cutter = thread_cutter()
    # Single-turn sweeps avoid unreliable long-helical-surface Booleans.
    # Adjacent turns share an identical radial profile at the seam.
    helices = [cutter.moved(b.Pos(x,y,-i*THREAD_PITCH))
               for x,y in ATTACH_XY for i in range(ceil(CLAMP_T/THREAD_PITCH)+1)]
    q = one(p.cut(*helices)).clean()
    assert q.is_valid and len(q.solids()) == 1
    assert p.volume-q.volume > 1.0, 'Thread cut must remove material from all four bore walls'
    q.label = p.label
    q.color = ALUMINUM_5052_COLOR
    return q


