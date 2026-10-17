"""Quad-turbo 8.0 L W16 — full sectioned assembly.

Thirteen system models, each its own file under `src/` with its own STEP,
composed here by CALLING them (occurrence order = explode order). The clips,
`ANIMATION` from `lib/animation.py`, move whole systems by these group names
and the block casting by its own (`#block_2`: it shares the block system's
name); the build bakes them to keyframes in the sidecar. Rebuilding a system
alone does not rebuild the engine — rerun this script to pick it up. The
section flag is `lib/spec.py:SECTIONED`.
    block          block + main caps + shells
    crank          crankshaft, damper, flywheel
    pistons        16 x piston/rings/pin/circlips/rod/cap/bolts/shells
    heads          two heads
    valvetrain     64 valves + springs + retainers + followers + HLAs
    cams           four camshafts + caps
    camdrive       sprockets, chains, guides, tensioners
    covers         cam covers, coils, plug wells, breathers
    oil_system     dry-sump pan, windage tray, pumps, filter
    turbos         four turbochargers
    exhaust        16 primaries, collectors, downpipes, shields
    induction      intercoolers, plenums, throttles, charge pipes, fuel rails
    ancillaries    alternator, water pumps, belt, coolant manifolds, bell housing
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from ancillaries import ancillaries
from block import block
from camdrive import camdrive
from cams import cams
from covers import covers
from crank import crank
from exhaust import exhaust
from heads import heads
from induction import induction
from oil_system import oil_system
from pistons import pistons
from turbos import turbos
from valvetrain import valvetrain

from lib.animation import ANIMATION


@step(out="../STEP/w16.step",
      animation=ANIMATION,
)
def w16():
    # Each call submits that system's build to the pool and returns at once;
    # the Compound below is where the assembly first reads geometry, so the
    # thirteen systems build in parallel and the assembly LINKS their trees.
    systems = [
        block(),
        crank(),
        pistons(),
        heads(),
        valvetrain(),
        cams(),
        camdrive(),
        covers(),
        oil_system(),
        turbos(),
        exhaust(),
        induction(),
        ancillaries(),
    ]
    return bd.Compound(children=systems, label="w16")


if __name__ == "__main__":
    w16()
