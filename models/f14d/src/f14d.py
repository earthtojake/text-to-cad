"""Grumman F-14D Super Tomcat -- full assembly.

Wings at 20 degrees, canopy closed, gear down, on the deck.  Clean airframe:
empty pylon stations, no external stores.

The airframe skin is ONE lofted solid (``src/lib/body.py``) built from
full-width blended sections, so the glove flows into the forward fuselage, the
nacelles flow into the pancake tunnel, and the fin roots sit on a continuous
surface.  Nothing in the primary surface is filleted, because nothing there is
joined.

Assembly tree is grouped BY SYSTEM -- ten sibling stages under ``src/``, each
a ``@memo`` function composed here by CALLING it.  THE ``SYSTEMS`` LIST BELOW
IS THE OCCURRENCE ORDER:

    airframe    the one-piece blended skin, cut and detailed
    cockpit     tub, panels, seats, HUD, canopy, windscreen
    wings       panels, slats, flaps, spoilers, tip lights
    inlets      ramps, splitters, bleed slots, ducts
    nozzles     C-D nozzles, petals, seals, actuator rings
    empennage   fins, rudders, stabilators, ventral fins
    aft         speed brakes, beavertail, tailhook, dump mast
    nose_gear   leg, wheels, launch bar, doors, bay
    main_gear   legs, wheels, brakes, doors, bays
    details     antennas, probes, lights, wicks, vents, panels

Three systems the brief names -- glove, engines, markings -- have no stage
yet; add one as ``src/<name>.py`` and insert it here.  A system that fails to
build fails the aircraft.

Which skin cutters the airframe applies is decided in ``src/airframe.py``.

Nothing about the aircraft articulates, so it has no mechanism.  The staged
teardown is the GLB's: ``teardown`` and ``explodedHold`` are animations
(``cadgen.gltf``) moving every system (the airframe too) and, on top, the part
groups the wings' and the aft section's second act separates.  It is one model,
``f14d``; STEP, GLB, STL and 3MF are written from its document on demand, and a GLB
export bakes the two animations into clips.
"""

from __future__ import annotations

import math
import re

from cadgen import model
from cadgen.gltf import animation

import build123d as bd

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

# Order here IS the occurrence order.
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
# The staged teardown
#
# Two acts on one master ramp (0 = built, 1 = fully apart). Act 1 separates the
# ten systems; act 2 breaks the wings and the aft section into their own parts,
# each group riding ON TOP of its system's act-1 travel. Every stage is a window
# on the ramp with a smoothstep ease, so the eye gets a sequence rather than a
# single pop; the acts overlap on purpose (act 1 spans [0, 0.58] of the ramp,
# act 2 [0.52, 1]).
#
# Every system moves, the airframe too, each along its vector in the world, which is
# the old clips' world-space motion exactly; each act-2 group moves on top of its
# system's travel, by its own vector. The old clips also faded the airframe to 22%
# opacity; a GLB has no opacity channel, so the airframe stays opaque.
# ---------------------------------------------------------------------------

ACT1_END = 0.58
ACT2_START = 0.52
ACT2_SPAN = 1 - ACT2_START

# system -> (stage window within act 1, explode vector in mm), in the order the
# old choreography staged them.
EXPLODE = {
    "airframe": ((0.0, 0.55), (-1400.0, 0.0, 5200.0)),    # one blended loft
    "cockpit": ((0.10, 0.62), (-500.0, 0.0, 2500.0)),     # tub, seats, canopy
    "wings": ((0.16, 0.68), (200.0, 0.0, 3300.0)),        # panels, slats, flaps
    "empennage": ((0.22, 0.74), (1900.0, 0.0, 2700.0)),   # fins, stabilators
    "nozzles": ((0.26, 0.78), (4400.0, 0.0, 300.0)),      # C-D petals, seals
    "aft": ((0.32, 0.84), (2700.0, 0.0, -600.0)),         # brakes, hook
    "inlets": ((0.38, 0.88), (-1000.0, 0.0, -2500.0)),    # ramps, ducts
    "main_gear": ((0.44, 0.92), (200.0, 0.0, -2300.0)),   # legs, doors, bays
    "nose_gear": ((0.48, 0.96), (-1900.0, 0.0, -1700.0)),  # leg, launch bar
    "details": ((0.52, 1.00), (0.0, 0.0, 1500.0)),        # antennas, lights
}

# Act-2 groups: (joint, system, label patterns, side, stage window within act 2,
# ADDITIVE explode vector in mm). A part is in a group when its label starts with
# one of the patterns (and holds ":<side>" where a side is given), as the old
# `render/subrefs.py` chose the occurrence ids the clips named. Anything mirrored
# port/stbd is its own group: one joint moves its group along one vector.
SUBS = (
    ("wing_spoilers", "wings", ("wing_spoiler",), None, (0.00, 0.42), (0.0, 0.0, 1100.0)),
    ("wing_slats", "wings", ("wing_slat", "slat_track", "slat_actuator_fairing"), None, (0.08, 0.52),
     (-1300.0, 0.0, 250.0)),
    ("wing_flaps", "wings", ("wing_flap", "flap_track_fairing"), None, (0.14, 0.58), (1500.0, 0.0, -450.0)),
    ("wingtip_port", "wings", ("wingtip_",), "port", (0.24, 0.66), (0.0, 1500.0, 250.0)),
    ("wingtip_stbd", "wings", ("wingtip_",), "stbd", (0.24, 0.66), (0.0, -1500.0, 250.0)),
    ("speedbrake_dorsal", "aft", ("speedbrake_dorsal",), None, (0.30, 0.72), (200.0, 0.0, 1500.0)),
    ("speedbrake_ventral_port", "aft", ("speedbrake_ventral_port",), None, (0.38, 0.80), (200.0, 1100.0, -1200.0)),
    ("speedbrake_ventral_stbd", "aft", ("speedbrake_ventral_stbd",), None, (0.38, 0.80),
     (200.0, -1100.0, -1200.0)),
    ("beavertail_panels", "aft", ("beavertail",), None, (0.48, 0.88), (1600.0, 0.0, 0.0)),
    ("tailhook", "aft", ("tailhook",), None, (0.56, 1.00), (800.0, 0.0, -1400.0)),
)
# How many parts each group held in the old clips (the occurrence ids they named).
SUB_COUNTS = {"wing_spoilers": 8, "wing_slats": 26, "wing_flaps": 10, "wingtip_port": 3, "wingtip_stbd": 3,
              "speedbrake_dorsal": 14, "speedbrake_ventral_port": 14, "speedbrake_ventral_stbd": 14,
              "beavertail_panels": 2, "tailhook": 12}


def _length(vector) -> float:
    return math.sqrt(sum(c * c for c in vector))


def _smoothstep(u: float) -> float:
    c = min(1.0, max(0.0, u))
    return c * c * (3.0 - 2.0 * c)


def _windowed(ramp: float, start: float, end: float) -> float:
    """A stage's own 0..1 progress, given the master ramp and the stage's window."""
    if end <= start:
        return 1.0 if ramp >= end else 0.0
    return _smoothstep((ramp - start) / (end - start))


def _explode(ramp: float) -> dict:
    """Every group's travel along its vector (mm) at one point on the master ramp, by its name
    (`explode_<system>`, or an act-2 group's)."""
    values = {}
    for system, ((start, end), vector) in EXPLODE.items():
        values[f"explode_{system}"] = _length(vector) * _windowed(ramp, start * ACT1_END, end * ACT1_END)
    for joint, _system, _patterns, _side, (start, end), vector in SUBS:
        values[joint] = _length(vector) * _windowed(ramp, ACT2_START + start * ACT2_SPAN, ACT2_START + end * ACT2_SPAN)
    return values


def _teardown(t: float) -> dict:
    # Out and back on a raised cosine, so the loop point is the built aircraft and
    # the reassembly is the teardown run backwards.
    return _explode(0.5 - 0.5 * math.cos(math.tau * t / 60.0))


def _exploded_hold(t: float) -> dict:
    # The same staging, stopping at full separation for a third of the clip.
    u = t / 24.0
    if u < 0.33:
        ramp = _smoothstep(u / 0.33)
    elif u < 0.67:
        ramp = 1.0
    else:
        ramp = 1.0 - _smoothstep((u - 0.67) / 0.33)
    return _explode(ramp)


def _descendants(node):
    for child in node.children:
        yield child
        yield from _descendants(child)


def _path(root, node) -> str:
    """``node``'s occurrence path below ``root``, as a ref's owner names it from ``root``'s
    label: each label down, numbered among the siblings that share it (``panel.2``)."""
    steps = []
    while node is not root:
        siblings = [child for child in node.parent.children if child.label == node.label]
        steps.append(node.label if len(siblings) == 1 else f"{node.label}.{siblings.index(node) + 1}")
        node = node.parent
    return "/".join([root.label, *reversed(steps)])


def _groups(aircraft, systems) -> dict:
    """Each teardown group's references in the aircraft and its unit vector: a system by its
    label, an act-2 group by its members' paths, chosen by label as the old clips chose them."""
    by_system = {system.label: system for system in systems}
    groups = {f"explode_{name}": ([f"{aircraft.label}/{name}"], vector) for name, (_stage, vector) in EXPLODE.items()}
    for group, system, patterns, side, _stage, vector in SUBS:
        members = [part for part in _descendants(by_system[system])
                   if any(re.match(pattern, part.label or "") for pattern in patterns)
                   and (side is None or f":{side}" in (part.label or ""))]
        if len(members) != SUB_COUNTS[group]:
            raise RuntimeError(f"teardown group {group!r} holds {len(members)} parts, not {SUB_COUNTS[group]}")
        groups[group] = ([_path(aircraft, part) for part in members], vector)
    return {name: (refs, tuple(c / _length(vector) for c in vector)) for name, (refs, vector) in groups.items()}


_KEY_STEP = 0.1  # s between the sampled keys of a teardown's channels


def _teardown_animation(aircraft, groups: dict, name: str, duration: float, explode_at) -> None:
    """A GLB animation of the teardown: each group's translation along its vector by
    ``explode_at(t)``'s travel, sampled every ``_KEY_STEP`` as LINEAR keys (a key whose
    neighbours hold its value is dropped), so the old clip's eases play as they were."""
    show = animation(aircraft, name, duration=duration)
    count = round(duration / _KEY_STEP)
    times = [duration * i / count for i in range(count + 1)]
    poses = [explode_at(t) for t in times]
    for group, (refs, unit) in groups.items():
        values = [pose[group] for pose in poses]
        kept = [i for i in range(len(times))
                if i in (0, len(times) - 1) or not values[i - 1] == values[i] == values[i + 1]]
        keys = [(times[i], tuple(c * values[i] for c in unit)) for i in kept]
        show.channel(refs, path="translation", keys=keys, interpolation="LINEAR")


@model
def f14d():
    groups = [system() for system in SYSTEMS]
    aircraft = bd.Compound(children=groups, label="f14d_super_tomcat")
    teardown = _groups(aircraft, groups)
    _teardown_animation(aircraft, teardown, "teardown", 60, _teardown)
    _teardown_animation(aircraft, teardown, "explodedHold", 24, _exploded_hold)
    return aircraft


if __name__ == "__main__":
    f14d()
