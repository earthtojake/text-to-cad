"""Grumman F-14D Super Tomcat -- full assembly.

Wings at 20 degrees, canopy closed, gear down, on the deck.  Clean airframe:
empty pylon stations, no external stores.

The airframe skin is ONE lofted solid (``src/lib/body.py``) built from
full-width blended sections, so the glove flows into the forward fuselage, the
nacelles flow into the pancake tunnel, and the fin roots sit on a continuous
surface.  Nothing in the primary surface is filleted, because nothing there is
joined.

Assembly tree is grouped BY SYSTEM — ten sibling models under ``src/``,
composed here by CALLING them — which is also how the animation moves
things: act 1 of the teardown moves one system per stage.

OCCURRENCE ORDER IS THE ``SYSTEMS`` LIST BELOW, and the clips take each
system's occurrence id from its place there:

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
yet; add one as ``src/<name>.py``, insert it here, and give it a stage in the
teardown's ``_ACT1`` table, or it sits still while the rest separates. A
system that fails to build fails the aircraft (nothing is skipped silently any
more; the store keeps the last good result of every other system, so the fix
rebuilds only the broken one).

Which skin cutters the airframe applies is decided in ``src/airframe.py``.

The aircraft declares NO kinematics: nothing about it articulates, and the
staged teardown is choreography, which lives whole in the ``ANIMATION`` clips
below, baked to keyframes in the model's sidecar when it builds.
"""

from __future__ import annotations

import functools
import math
from fnmatch import fnmatchcase

import cadgen
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
# links its tree. Adding a system here renumbers everything after it; the
# clips below take every occurrence id from this list, so they follow.
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


# ---------------------------------------------------------------------------
# Animation: the staged teardown, sampled to keyframes when the model builds.
#
# Nothing here is a joint: the whole thing is a staged separation, so it is
# choreography end to end and the model declares no mates at all.
#
# Two acts on one master ramp. Act 1 separates the ten systems; act 2 breaks
# the wings and the aft section into their own parts. Every stage is a WINDOW
# on the ramp with a smoothstep ease, so the eye gets a sequence rather than a
# single pop; the acts overlap on purpose (act 1 spans [0, 0.58] of the ramp,
# act 2 [0.52, 1]).
# ---------------------------------------------------------------------------

_ACT1_END = 0.58
_ACT2_START = 0.52
_ACT2_SPAN = 1 - _ACT2_START

# Act 1: system, its stage window within act 1, its explode vector in mm.
_ACT1 = (
    (airframe, (0.00, 0.55), (-1400, 0, 5200)),    # one blended loft
    (cockpit, (0.10, 0.62), (-500, 0, 2500)),      # tub, seats, canopy
    (wings, (0.16, 0.68), (200, 0, 3300)),         # panels, slats, flaps
    (empennage, (0.22, 0.74), (1900, 0, 2700)),    # fins, stabilators
    (nozzles, (0.26, 0.78), (4400, 0, 300)),       # C-D petals, seals
    (aft, (0.32, 0.84), (2700, 0, -600)),          # brakes, hook
    (inlets, (0.38, 0.88), (-1000, 0, -2500)),     # ramps, ducts
    (main_gear, (0.44, 0.92), (200, 0, -2300)),    # legs, doors, bays
    (nose_gear, (0.48, 0.96), (-1900, 0, -1700)),  # leg, launch bar
    (details, (0.52, 1.00), (0, 0, 1500)),         # antennas, lights
)

# Act 2: stage window within act 2, ADDITIVE explode vector, and the name
# patterns of the parts it moves. These ride ON TOP of their system's act-1
# travel, so the wing parts keep travelling with the wing while separating
# from it. No one group holds "every slat track on both wings", so a stage
# picks its parts by name, out of the built tree's.
#
# Anything mirrored port/stbd is its own stage: one handle moves every part it
# names by the SAME vector, so a single "wingtips" stage would push the port
# tip outboard and the starboard tip straight through the wing.
_ACT2 = (
    ((0.00, 0.42), (0, 0, 1100), ("wing_spoiler:*",)),
    ((0.08, 0.52), (-1300, 0, 250),
     ("wing_slat:*", "slat_track:*", "slat_actuator_fairing:*")),
    ((0.14, 0.58), (1500, 0, -450), ("wing_flap:*", "flap_track_fairing:*")),
    ((0.24, 0.66), (0, 1500, 250), ("wingtip_*:port",)),  # lights + housing
    ((0.24, 0.66), (0, -1500, 250), ("wingtip_*:stbd",)),
    ((0.30, 0.72), (200, 0, 1500), ("speedbrake_dorsal_*",)),
    ((0.38, 0.80), (200, 1100, -1200), ("speedbrake_ventral_port_*",)),
    ((0.38, 0.80), (200, -1100, -1200), ("speedbrake_ventral_stbd_*",)),
    ((0.48, 0.88), (1600, 0, 0), ("beavertail_access_panel:*",)),
    ((0.56, 1.00), (800, 0, -1400), ("tailhook_*",)),  # hook + bay doors
)

# The skin reaches minimum opacity well before it finishes travelling, so the
# internals are readable while it is still clearing them.
_SKIN_FADE_WINDOW = (0.0, 0.45)
_SKIN_OPACITY = (1.0, 0.22)

_TEARDOWN_S = 60.0
_HOLD_S = 24.0


def _system(model) -> str:
    """A system's target: the occurrence its place in SYSTEMS gives it."""
    return f"#o1.{SYSTEMS.index(model) + 1}"


def _smoothstep(u: float) -> float:
    c = min(1.0, max(0.0, u))
    return c * c * (3.0 - 2.0 * c)


def _windowed(ramp: float, start: float, end: float) -> float:
    """A stage's own 0..1 progress, given the master ramp and its window."""
    if end <= start:
        return 1.0 if ramp >= end else 0.0
    return _smoothstep((ramp - start) / (end - start))


@functools.cache
def _act2_parts(labels: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Each act-2 stage's targets: every name in the built tree one of its
    patterns matches. The names are the same at every sample, so they are
    matched once per tree."""
    stages = []
    for _window, _vector, patterns in _ACT2:
        names = tuple(f"#{name}" for name in labels
                      if any(fnmatchcase(name, p) for p in patterns))
        if not names:
            raise ValueError(f"teardown stage {' '.join(patterns)} names no part")
        stages.append(names)
    return tuple(stages)


def _explode(m, ramp: float) -> None:
    """The whole staged separation at one point on the master ramp (0 = built,
    1 = fully apart). Shared by both clips, which differ only in how they walk
    the ramp."""
    for system, (start, end), vector in _ACT1:
        progress = _windowed(ramp, start * _ACT1_END, end * _ACT1_END)
        if progress > 0:
            m.get(_system(system)).translate([c * progress for c in vector])
    stages = zip(_ACT2, _act2_parts(tuple(m.labels())))
    for ((start, end), vector, _patterns), parts in stages:
        progress = _windowed(ramp, _ACT2_START + start * _ACT2_SPAN,
                             _ACT2_START + end * _ACT2_SPAN)
        if progress > 0:
            m.get(*parts).translate([c * progress for c in vector])
    fade = _windowed(ramp, *_SKIN_FADE_WINDOW)
    opaque, faded = _SKIN_OPACITY
    m.get(_system(airframe)).opacity(opaque + (faded - opaque) * fade)


def _teardown(t: float, m) -> None:
    # Out and back on a sine, so the loop point is the built aircraft and the
    # reassembly is the teardown run backwards.
    _explode(m, 0.5 - 0.5 * math.cos(math.tau * (t / _TEARDOWN_S)))


def _exploded_hold(t: float, m) -> None:
    # The same staging, but it stops at full separation and sits there for a
    # third of the clip -- the shape you want for a still review or a talk.
    u = t / _HOLD_S
    if u < 0.33:
        ramp = _smoothstep(u / 0.33)
    elif u < 0.67:
        ramp = 1.0
    else:
        ramp = 1.0 - _smoothstep((u - 0.67) / 0.33)
    _explode(m, ramp)


ANIMATION = {
    # 60 s: a published frame of this 2,392-record assembly costs far more than
    # a display frame, so the clip is stretched to keep the per-frame delta
    # small at the paced-down playback rate.
    "teardown": cadgen.clip(_teardown, duration=_TEARDOWN_S, label="Staged teardown"),
    "explodedHold": cadgen.clip(_exploded_hold, duration=_HOLD_S, label="Exploded hold"),
}


@step(out="../STEP/f14d.step", animation=ANIMATION)
def f14d():
    groups = [system() for system in SYSTEMS]
    return bd.Compound(children=groups, label="f14d_super_tomcat")


if __name__ == "__main__":
    f14d()
