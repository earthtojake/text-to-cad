"""Grumman F-14D Super Tomcat -- full assembly.

Wings at 20 degrees, canopy closed, gear down, on the deck.  Clean airframe:
empty pylon stations, no external stores.

The airframe skin is ONE lofted solid (``src/lib/body.py``) built from
full-width blended sections, so the glove flows into the forward fuselage, the
nacelles flow into the pancake tunnel, and the fin roots sit on a continuous
surface.  Nothing in the primary surface is filleted, because nothing there is
joined.

Assembly tree is grouped BY SYSTEM — ten sibling models under ``src/``,
composed here by CALLING them — which is also how ``f14d.anim.js`` moves
things: act 1 of the teardown addresses one system per ref.

OCCURRENCE ORDER IS THE ``SYSTEMS`` LIST BELOW, and the animation module's
occurrence refs are numbered against it:

    o1.1  airframe    the one-piece blended skin, cut and detailed
    o1.2  cockpit     tub, panels, seats, HUD, canopy, windscreen
    o1.3  wings       panels, slats, flaps, spoilers, tip lights
    o1.4  inlets      ramps, splitters, bleed slots, ducts
    o1.5  nozzles     C-D nozzles, petals, seals, actuator rings
    o1.6  empennage   fins, rudders, stabilators, ventral fins
    o1.7  aft         speed brakes, beavertail, tailhook, dump mast
    o1.8  nose_gear   leg, wheels, launch bar, doors, bay
    o1.9  main_gear   legs, wheels, brakes, doors, bays
    o1.10 details     antennas, probes, lights, wicks, vents, panels

Three systems the brief names -- glove, engines, markings -- have no model
yet; add one as ``src/<name>.py`` and insert it here, renumbering
``f14d.anim.js`` in the same commit. A system that fails to build fails the
aircraft (nothing is skipped silently any more; the store keeps the last good
result of every other system, so the fix rebuilds only the broken one).

Which skin cutters the airframe applies is decided in ``src/airframe.py``.

The aircraft declares NO kinematics: nothing about it articulates, and the
staged teardown is choreography, which lives whole in ``f14d.anim.js``.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from aft import aft
from airframe import airframe
from cockpit import cockpit
from details import details
from empennage import empennage
from inlets import inlets
from main_gear import main_gear
from nose_gear import nose_gear
from nozzles import nozzles
from wings import wings

# Order here IS the occurrence order (o1.1, o1.2, ...). Every entry is a
# sibling model under src/; calling it inside the body builds it if stale (on
# its own worker, in parallel with the rest) or loads it, and the aircraft
# links its tree. Adding a system here renumbers everything after it, and
# f14d.anim.js must be renumbered in the same commit.
SYSTEMS = [
    airframe,
    cockpit,
    wings,
    inlets,
    nozzles,
    empennage,
    aft,
    nose_gear,
    main_gear,
    details,
]


@step(out="../STEP/f14d.step", animation="f14d.anim.js")
def f14d():
    groups = [system() for system in SYSTEMS]
    return bd.Compound(children=groups, label="f14d_super_tomcat")


if __name__ == "__main__":
    f14d()
