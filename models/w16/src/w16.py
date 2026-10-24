"""Quad-turbo 8.0 L W16 — full sectioned assembly.

Thirteen systems, each a `@memo` stage in its own file under `src/`, composed
here by CALLING them (occurrence order = the original's explode order). The
museum section is one flag, `lib/spec.py:SECTIONED`, read by every system: the
cutaway is the model's own geometry. The engine is one model, `w16`, holding
the `crank` motion and the `explode` and `running_reveal` GLB animations below; its GLB,
whose clips they are, is exported on demand (`cadgen export <id> GLB/w16.glb`, the id its
run prints).
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

from cadgen import model
from cadgen.ap242 import configuration_sequence

import build123d as bd

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

from lib import explode, kinematics
from lib.palette import apply_finishes

# Order here IS the occurrence order.
SYSTEMS = [
    block,
    crank,
    pistons,
    heads,
    valvetrain,
    cams,
    camdrive,
    covers,
    oil_system,
    turbos,
    exhaust,
    induction,
    ancillaries,
]


@model
def w16():
    systems = [system() for system in SYSTEMS]
    engine = bd.Compound(children=systems, label="w16")
    apply_finishes(engine)
    kinematics.author_joints(engine)
    turbo_tags = kinematics.turbos(engine)
    # One full four-stroke cycle, 720 deg in 6 s: the pistons and rods in the firing
    # order, the cams at half speed, 64 valves and their followers, the sprockets, the oil
    # pump, the turbo rotors and every accessory pulley. It ends where it starts, so a
    # player repeats it exactly (a motion has no loop of its own).
    configuration_sequence(engine, "crank", kinematics.crank_cycle(turbo_tags), duration=kinematics.CRANK_SECONDS)
    # The staged explode, 12 s with the engine running throughout, and the running
    # cutaway, 24 s: the bodywork off, held and back on while the engine runs, ending where
    # it starts: GLB animations (`lib/explode.py`).
    explode.explode_animation(engine, turbo_tags)
    explode.running_reveal_animation(engine, turbo_tags)
    return engine


if __name__ == "__main__":
    w16()
