"""Quad-turbo 8.0 L W16 — full sectioned assembly.

Groups (occurrence order = explode order; the anim targets these ids):
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
from cadgen.compose import memo

from lib import ancillaries, block, bottom_end, camdrive, cams, covers, exhaust, heads, induction, oil_system, pistons, turbos, valvetrain

SECTIONED = True

_BLOCK = memo(block.build)
_BOTTOM = memo(bottom_end.build)
_PISTONS = memo(pistons.build)
_HEADS = memo(heads.build)
_VALVES = memo(valvetrain.build)
_CAMS = memo(cams.build)
_CAMDRIVE = memo(camdrive.build)
_COVERS = memo(covers.build)
_OIL = memo(oil_system.build)
_TURBOS = memo(turbos.build)
_EXHAUST = memo(exhaust.build)
_INDUCTION = memo(induction.build)
_ANCILLARIES = memo(ancillaries.build)


def group(label, children):
    """A labelled sub-assembly node; an EMPTY group has a null TopoDS and would
    crash the assembly, so a stub module contributes nothing instead."""
    kids = [c for c in children if c is not None]
    if not kids:
        return None
    return bd.Compound(children=kids, label=label)


@step(out="../STEP/w16.step", kind="assembly", animation="w16.anim.js",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def w16():
    groups = [
        group("block", _BLOCK(SECTIONED)),
        group("crank", _BOTTOM(SECTIONED)),
        group("pistons", _PISTONS()),
        group("heads", _HEADS(SECTIONED)),
        group("valvetrain", _VALVES()),
        group("cams", _CAMS(SECTIONED)),
        group("camdrive", _CAMDRIVE(SECTIONED)),
        group("covers", _COVERS(SECTIONED)),
        group("oil_system", _OIL(SECTIONED)),
        group("turbos", _TURBOS(SECTIONED)),
        group("exhaust", _EXHAUST(SECTIONED)),
        group("induction", _INDUCTION(SECTIONED)),
        group("ancillaries", _ANCILLARIES(SECTIONED)),
    ]
    return bd.Compound(children=[g for g in groups if g is not None], label="w16")
