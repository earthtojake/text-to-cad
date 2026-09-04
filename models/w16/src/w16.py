"""Quad-turbo 8.0 L W16 — full sectioned assembly.

Thirteen system models, each its own file under `src/` with its own STEP,
composed here by CALLING them (occurrence order = explode order; the anim
targets these ids). Rebuilding a system alone does not rebuild the engine —
rerun this script to pick it up. The section flag is `lib/spec.py:SECTIONED`.
    o1.1  block          block + main caps + shells
    o1.2  crank          crankshaft, damper, flywheel
    o1.3  pistons        16 x piston/rings/pin/circlips/rod/cap/bolts/shells
    o1.4  heads          two heads
    o1.5  valvetrain     64 valves + springs + retainers + followers + HLAs
    o1.6  cams           four camshafts + caps
    o1.7  camdrive       sprockets, chains, guides, tensioners
    o1.8  covers         cam covers, coils, plug wells, breathers
    o1.9  oil_system     dry-sump pan, windage tray, pumps, filter
    o1.10 turbos         four turbochargers
    o1.11 exhaust        16 primaries, collectors, downpipes, shields
    o1.12 induction      intercoolers, plenums, throttles, charge pipes, fuel rails
    o1.13 ancillaries    alternator, water pumps, belt, coolant manifolds, bell housing
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


@step(out="../STEP/w16.step", kind="assembly",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
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
